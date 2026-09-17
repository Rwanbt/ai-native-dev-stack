# Distribution & Lifecycle

How the AI Native Dev Stack is installed, chosen, changed, updated and removed.
The decisions behind it are in [ADR-0009](adr/0009-distribution-profiles-and-lifecycle-ownership.md);
this document is the operating manual.

---

## 1. Two profiles

```
AI Native Dev Stack
        │
        ├── Standard
        │     context · memory · skills · hooks · adapters · AI docs · methodologies
        │
        └── Verified
              Standard
                 +  Verified Work Plane · project trust · Work Contracts
                    Verification Runner · evidence · traceability · convergence
```

**Verified extends Standard. Standard never depends on Verified.**

That inheritance is real, not a diagram: the `verified` profile declares
`extends: "standard"` and lists only what it adds, the resolver computes the
effective set, and the CLI dispatcher loads `ainative_workplane` lazily — so
`ainative init --profile standard` never imports a single authority module.
`tests/test_lifecycle_cli.py::LayerBoundary` proves both directions by
inspecting `sys.modules` after the import.

### Which one should I choose?

| | Standard | Verified |
|---|---|---|
| For | students, individual developers, normal AI coding, fast setup | production, teams, critical code, autonomous agents, auditability |
| Gives you | the context, memory and skills that make an AI work well *with* your project | all of that, plus governance and deterministic verification of declared work |
| Costs you | nothing beyond the files it installs | a human trust bootstrap, and the discipline of declaring work before doing it |

> Standard optimizes **how AI works with the project**.
> Verified additionally **governs and deterministically verifies declared work**.

Switching between them is reversible and non-destructive in both directions.

---

## 2. The commands

```bash
ainative init                          # asks which profile
ainative init --profile standard       # non-interactive
ainative init --profile verified

ainative status                        # what is installed, and its health
ainative status --json
ainative profile status
ainative profile switch verified
ainative profile switch standard
ainative profile purge verified        # delete Verified data — explicit, never implied

ainative doctor                        # diagnose; changes nothing
ainative repair                        # fix what doctor reports

ainative update check                  # is a newer release available?
ainative update                        # apply it, transactionally
ainative update rollback               # restore the project assets it replaced

ainative uninstall                     # remove the stack, keep your work
ainative uninstall --purge --yes       # full project-level cleanup
```

Every mutation takes `--dry-run`. Every confirmation takes `--yes`. Every
command a script would parse takes `--json`. Nothing ever blocks on a prompt
without a terminal.

The Verified Work Plane commands are unchanged and reach the same engine they
always did:

```bash
ainative trust bootstrap ...    ainative work new ...      ainative verify ...
ainative trust show ...         ainative work admit ...    ainative converge ...
                                ainative work update ...   ainative debug ...
```

---

## 3. The component model

A profile is a list of component identifiers. A component says where content
comes from, where it lands, and who owns the result.

| Field | Meaning |
|---|---|
| `kind` | `tree` · `file` · `template` · `external_block` · `marker` · `data_root` |
| `source` | path inside the distribution |
| `destination` | path inside the project |
| `ownership` | one of the four classes below |
| `include` | for a `tree`, the exact files to take (otherwise: all of them) |
| `executable` | filenames to chmod +x on POSIX |
| `required` | whether a profile is incomplete without it |

The manifests are `ainative/lifecycle/data/components.json` and `profiles.json`.
They are validated at load: an unknown kind, an unknown ownership class, a
missing parent, an inheritance cycle, a destination that escapes the project, or
two destinations that collide under case-folding are all refusals.

Components shipped today:

| Component | Profile | Kind | Ownership | Destination |
|---|---|---|---|---|
| `ai-docs-tooling` | standard | tree | MANAGED_IMMUTABLE | `tools/ai_docs/` |
| `engineering-method` | standard | file | MANAGED_MUTABLE | `AGENTS.md` |
| `conventions` | standard | file | MANAGED_MUTABLE | `conventions.json` |
| `context-template` | standard | tree | MANAGED_IMMUTABLE | `.ai-native/templates/` |
| `skills-claude` | standard | tree | MANAGED_IMMUTABLE | `.claude/skills/` |
| `skills-agents` | standard | tree | MANAGED_IMMUTABLE | `.agents/skills/` |
| `machine-config` | standard | template | USER_DATA | `tools/ai_docs/config.sh` |
| `gitignore-entry` | standard | external_block | EXTERNAL_CONFIG | `.gitignore` |
| `claude-hook` | standard | json_hook | EXTERNAL_CONFIG | `.claude/settings.json` |
| `verified-workplane` | verified | marker | MANAGED_IMMUTABLE | `.ai-native/lifecycle/verified.json` |
| `verified-guide` | verified | file | MANAGED_IMMUTABLE | `.ai-native/docs/VERIFIED-WORK-PLANE.md` |
| `verified-data` | verified | data_root | USER_DATA | `.ai-native/{trust,work,runs}` |

---

## 4. Ownership — the rule everything else rests on

Without a recorded digest, "which files does the stack own?" is unanswerable,
and every uninstall or update becomes a guess. So each managed path is
classified and its content hashed at the moment the stack writes it.

| Class | Update behaviour | Default uninstall |
|---|---|---|
| `MANAGED_IMMUTABLE` | replaced only when the file still holds the bytes we wrote | removed only when unchanged |
| `MANAGED_MUTABLE` | never silently overwritten; a changed file keeps its content and gets `<name>.new` beside it | preserved if changed, removed if unchanged |
| `USER_DATA` | never touched | never removed; `--purge` only |
| `EXTERNAL_CONFIG` | only the delimited region is rewritten | only the region is taken back, byte for byte (one exception below) |

Comparing `digest_at_install` with the bytes on disk yields one of four states:

```
UNCHANGED       the file still holds what we wrote      → safe to replace, safe to remove
USER_MODIFIED   the user edited it                      → never replaced, never removed
MISSING         recorded but absent                     → repair can restore it
CONFLICT        present, but its install digest is unknown → left alone
```

`created_by_ainative` is a separate flag, and it is what protects an adopted
legacy install: a file recorded because it sat where a managed file goes, but
whose bytes the stack never wrote, is never replaced and never removed — not by
an update, not by an uninstall, not by `--purge`.

### External config: `.gitignore`

The stack writes a delimited region and remembers only that region:

```
# my project ignores
*.log

# >>> BEGIN ai-native-dev-stack (managed — do not edit inside)
tools/ai_docs/config.sh
.ai-native/lifecycle/backups/
.ai-native/lifecycle/update-cache.json
# <<< END ai-native-dev-stack
```

`apply` and `remove` are exact inverses, with one stated exception: a file that
did **not** end with a newline gets one, and keeps it after the region is
removed. `abc` becomes `abc
`. The alternative is appending the block to the
file's last line, which corrupts that line — so the newline is added
deliberately, and it is the only byte outside the managed region that any
lifecycle operation ever changes.

Everything else is exact, including CRLF: the file is read and written with no
newline translation, and the block is rendered with whatever line ending the
file already uses.

---

## 5. Transactions

Every mutation runs as:

```
inspect → plan → validate → backup → stage → apply → verify → commit state
                                                              └── last, always
```

* **Backup first.** Anything about to be replaced or deleted is copied into
  `.ai-native/lifecycle/backups/<transaction>/` before the first write. Rollback
  is a copy back, not a reconstruction.
* **State last.** The install state is written only after every change landed
  and was re-read. Until that write, the on-disk state still describes the
  previous install — so an interruption *is* a rollback that has not run yet.

The journal at `.ai-native/lifecycle/transactions/<id>.json` records:

```
operation · from_profile · to_profile · planned_changes · completed_changes
backup_location · state_backed_up · state · started_at · finished_at · stack_version
```

The install state is backed up alongside the files, so reversing a transaction
puts the record back as well as the bytes. It is also the only record of a
reversible update: `ainative update rollback` reads the journal rather than a
second file written after the commit.

States: `PREPARED → APPLYING → COMMITTED | ROLLED_BACK`. Anything found in
`APPLYING` at the next run is `INTERRUPTED`, which blocks further mutation
(exit code 3) until `ainative repair` completes the recovery from the journal's
recorded backup. The last 5 journals and their backups are retained; an
interrupted one is never pruned.

### Concurrency

One lifecycle mutation at a time, per canonical project path. The long-lived logical
claim at `.ai-native/lifecycle/lifecycle.lock` records pid, host, operation,
acquisition time, and a UUID `claim_id` unique to that acquisition. Time answers
*when*; `claim_id` answers *which exact claim owns the lock*.

Creating, reclaiming, force-replacing, and releasing that claim are serialized
by a separate short-lived OS lock. Its stable per-project key is derived from
the resolved project path, and its file lives under the system temporary
directory rather than inside the project. The OS guard is held only while the
claim changes, never while the lifecycle operation changes project files. This
closes the compare-then-delete window in which an old owner could remove a
replacement owner's claim.

A lock whose owner is *provably* gone is reclaimed automatically. A lock whose
owner is alive, or cannot be judged (another host, an unreadable process table),
is left alone and reported. `--force-unlock` is an operator override: use it
only after independently establishing that the previous lifecycle operation is
no longer allowed to mutate the project.

---

## 6. Standard → Verified → Standard

**Upgrading** installs only the delta. Standard components are untouched, no
file is reinstalled, and the operation is idempotent.

**Downgrading** removes the Verified integration and preserves everything else:

```
removed     .ai-native/lifecycle/verified.json
            .ai-native/docs/VERIFIED-WORK-PLANE.md
preserved   .ai-native/trust/     approval roots, trust anchor
            .ai-native/work/      contracts, revisions, approvals
            .ai-native/runs/      verification evidence
```

That preserved state is **dormant**, not deleted.

> Switching to Standard disables active Verified governance but preserves the
> historical audit trail so the project may return to Verified later.

`ainative profile switch verified` reactivates it. The historical Work
revisions, run evidence and approval records are never rewritten to make a
downgrade, an update or an uninstall succeed.

Deleting that data is a separate command that names the exact paths first,
requires `--yes` without a terminal, and supports `--dry-run`:

```bash
ainative profile purge verified --dry-run
ainative profile purge verified --yes
```

### The profile is not the authority

`active_profile = verified` records that Verified integration is active. It is
**not** evidence of trust. The lifecycle layer will not write a trust anchor, an
approval root, an approval, a work contract, a verification run or a convergence
record — bootstrap is a privileged human act the Work Plane cannot attribute
(ADR-0006), so an installer that performed it would be manufacturing the one
fact the architecture refuses to manufacture. `ainative init --profile verified`
prepares the environment and then says:

```
Verified is active, but this project has no trust anchor yet. Trust bootstrap is
a privileged human act: the Work Plane cannot verify who performed it, so the
installer will not perform it for you (ADR-0006).
  ainative trust bootstrap --repo . --approval-root <file> --policy <file> \
      --by "<you>" --signer <fingerprint>
```

Equally, Standard never fabricates a convergence, a work contract or a trust
state to look like Verified.

---

## 7. Uninstall

```bash
ainative uninstall --dry-run     # review first
ainative uninstall
```

Removes: unmodified managed runtime files, managed adapters and generated
tooling, managed regions in files it does not own, the active lifecycle
integration.

Preserves: user-modified managed files, `USER_DATA`, your vault and memory,
Work history, trust and audit history, custom config, and everything the stack
never wrote.

```
Removed: 32
Preserved user-modified: 1
Preserved user-data: 4
```

```bash
ainative uninstall --purge --yes
```

Additionally deletes the **data roots the manifests declare** —
`.ai-native/{trust,work,runs}` — and the lifecycle's own bookkeeping
(`state.json`, the journal, the backups, the update cache), named one by one
rather than by emptying the directory.

What `--purge` does **not** widen: it still never removes a file the stack did
not write, and it still never removes a managed file you edited. Its extra
reach is over declared data roots, not over everything on disk. So
`tools/ai_docs/config.sh` — your machine config, seeded from a template —
survives a purge, and so does an `AGENTS.md` you customised.

**`git clean`, `git checkout .` and `git restore .` are prohibited as uninstall
or update mechanisms.** They operate on your whole working tree rather than on
what the stack owns, and would destroy unrelated uncommitted work. The ownership
manifest is the only mechanism.

The lifecycle layer also never runs `git commit`, `git push`, `git reset` or
`git clean` in your project. It is not a Git orchestrator.

---

## 8. Updates

```bash
ainative update check       # UP_TO_DATE | UPDATE_AVAILABLE | OFFLINE | CHECK_FAILED | DISABLED
ainative update --dry-run
ainative update
ainative update rollback
```

**Detection is automatic; application never is.** A check is cached at
`.ai-native/lifecycle/update-cache.json` (default TTL 24 h) and bounded by a
5-second timeout. `OFFLINE` and `CHECK_FAILED` are outcomes, not errors.

```
AI Native 1.4.0 is available.
Current: 1.3.2
Run `ainative update`
```

Preferences live in the install state:

```json
"update_preferences": {
  "enabled": true, "auto_check": true, "check_interval": 86400, "channel": "stable"
}
```

`AINATIVE_NO_UPDATE_CHECK=1` disables every network check — for CI and offline
machines. When `GITHUB_TOKEN` or `GH_TOKEN` is present in the environment, the
check sends it as a bearer token (many users share one NAT address and hit the
anonymous rate limit); the token is never logged, never written to the cache,
and never included in an error message. A 403/429 answer is reported as a
rate-limit diagnosis with the same remedy.

### Sources and credential confinement

The source is selected by one environment variable, with no discovery:

```text
AINATIVE_UPDATE_PROVIDER=local  + AINATIVE_UPDATE_LOCAL_DIR   → local mirror
AINATIVE_UPDATE_PROVIDER=github (default)                     → official releases
AINATIVE_UPDATE_URL                                           → custom release document
```

`AINATIVE_UPDATE_URL` names a custom HTTPS source whose release document is
GitHub-Release-API-compatible. It is **anonymous by construction**: it never
receives `GITHUB_TOKEN`, `GH_TOKEN` or any other provider credential, because
its metadata may name any artifact URL and that must not be enough to obtain a
token. The credential is sent to exactly one origin — `api.github.com`, the
built-in endpoint's declared `auth_origin` — and nowhere else, on any hop:

- release metadata may only redirect within its own origin; a cross-origin
  metadata redirect is refused;
- a release artifact may redirect across origins (GitHub answers `302` to its
  CDN): the redirect is followed anonymously, with every credential stripped;
- private GitHub release assets are fetched through the release asset API with
  `Accept: application/octet-stream`; the browser download URL is never
  authenticated;
- `https → http` downgrades, URLs carrying `user:password@`, and redirect
  chains beyond the bound are refused before a socket is opened.

There is no unverified fallback: a source that cannot publish the bundle's
SHA-256 is refused rather than trusted.

`ainative update check` exits 0 whatever the answer: `exit 0` means "the answer
is what it is", never "the source was reachable". A CI gate that needs the
second statement runs `ainative update check --strict`, which exits 1 on
`OFFLINE` / `CHECK_FAILED`.

### No network inside an authority command

`ainative verify`, `ainative converge`, `ainative trust` and `ainative work`
never trigger an update check. A verdict-producing command that reaches the
network has added a non-deterministic, externally-controlled input to an
authoritative surface. The dispatcher routes those commands before any
lifecycle module is imported, and a test breaks `urlopen` and runs them to prove
it. They may display an already-cached notice; nothing more.

### Applying

```
resolve release → runtime contract check → check → download → verify digest
      → validate archive paths → extract to a staging directory
      → bundle version check → build the plan → backup
      → transactional apply → commit state → record rollback metadata
```

There is no `curl … | overwrite project` anywhere in this path. Everything
that can refuse happens before the first project write: a refused update -
wrong runtime, wrong version, bad digest, bad archive - leaves the project
byte-identical, cache included.

**The artifact, stated precisely.** The official provider consumes the release's
declared pair: the external manifest `ainative-release-v3.json` published beside
the wheel, the sdist and the lifecycle bundle `ainative-lifecycle-v3-<version>.zip`,
each named for the release's own version. The manifest is parsed only after its
anchor — the SHA-256 and size the provider's own metadata reports for it — is
verified; it then declares the bundle's name, version, SHA-256 and size, and the
bundle is verified against that declaration. Inside the bundle, a
`lifecycle-protocol.json` document names the protocol version, the release
version and the payload root (`stack/`), and the payload's `VERSION` is compared
with the release again. A bridge release can still be built with `--protocol 2`
(`ainative-lifecycle-v2-<version>.zip`, no manifest) so older runtimes have the
documented upgrade stop.

**Containment of pre-2.2.2 runtimes, stated precisely.** Runtimes up to v2.2.2
looked for `ainative-dev-stack-*.zip` and found their payload by taking the
single top-level directory that held a `VERSION` file. A protocol v2 bundle
matches neither rule, so such a runtime refuses it with zero project writes even
when a mirror hands it the file directly. v2.2.2 itself refuses a v2 release at
the runtime gate (`CLI_UPDATE_REQUIRED`) before the download. The documented
path is always the same: upgrade the CLI first, then update each project. A release whose
tag says 2.2.2 and whose bundle says 2.2.1 is refused with
`UPDATE_VERSION_MISMATCH` before any download; so is a bundle whose internal
`VERSION` file disagrees with the release it declared, and so is a local
mirror whose index declares one version and names another version's archive.
Its SHA-256 must be published by the source (the release asset digest); a
release whose bundle carries no digest, or no bundle at all, is refused with
`UPDATE_INTEGRITY_METADATA_MISSING` before any download. There is no `zipball`
fallback and no unverified path. The internal mirror contract is the same: a
`releases.json` channel without a valid `sha256` is refused.

**The runtime must be the target.** Applying release N+1 is done by the
lifecycle code of N+1: the manifests, the planner and the transaction engine
ship inside the Python package. The updater therefore requires the installed
runtime to be exactly the target release version and refuses any other with
`CLI_UPDATE_REQUIRED`, before the download. The rule is strict equality, not a
compatibility matrix: no release has needed one, and a silent permission
system is the failure mode this refusal removes. Detection is unaffected -
`update check`, `status --check-updates` and `doctor --check-updates` work
with any runtime and say when a CLI upgrade is required first:

```bash
pip install --upgrade "git+https://github.com/Rwanbt/ai-native-dev-stack.git@v2.2.2"
cd your-project && ainative update
```

**A newer lifecycle protocol, stated precisely.** A release that publishes a
lifecycle bundle or manifest for a protocol newer than the running runtime's
(the current line is protocol 3: `ainative-lifecycle-v3-*`,
`ainative-release-v3.json`) is not a broken release *to a runtime that knows
the bridge*: `update check` reports it as available with a CLI upgrade
required, and `ainative update` refuses it with `CLI_UPDATE_REQUIRED`, before
any download or write, naming the upgrade command. A runtime older than the
bridge release has no such vocabulary and refuses it fail-closed (`CHECK_FAILED:
release publishes no ainative-lifecycle-v2-*.zip lifecycle bundle` on
`update check`); its documented escape path is the same upgrade command,
applied manually, then `ainative update`. A release that publishes no
lifecycle bundle at all keeps its refusal:
`UPDATE_INTEGRITY_METADATA_MISSING`. Before the first V3 publication the
release workflow verifies the declared `V3_BRIDGE_RELEASE` with
`scripts/check_bridge_release.py`, which resolves it through these same
selection rules and blocks the publication (`BLOCK RELEASE`) when the bridge
cannot be verified.

**The release chain, stated precisely.** For a published release:

```
tag == VERSION == ainative.__version__ == wheel/sdist metadata
    == bundle filename version == bundle internal VERSION
```

`scripts/check_release_versions.py` enforces the whole chain in the release
workflow, before publishing and again over the built artifacts; a tag that
does not name the tree's `VERSION` fails the release even when it points at
`main`.
**Integrity, stated precisely.** SHA-256 over the release archive proves the
bytes are the bytes the source described, and the archive's entry names are
validated by the same containment rule as every other destination (an entry
named `../../etc/cron.d/x` is refused before extraction, and so are archives
over the entry-count or expanded-size limits). This protects against a
corrupted, truncated or substituted archive on the wire. It does **not** protect
against a compromised release source: an attacker who controls the source
controls both the archive and the digest it publishes. Signature verification is
not implemented and is not claimed.

**Your edits during an update.** A `MANAGED_MUTABLE` file whose digest no longer
matches keeps its content; the new version is written beside it as
`<name>.new` and the path is reported as a conflict. No merge is attempted —
a deterministic merge of arbitrary content is not available here, and an LLM
merge has no place in a core that must produce the same result twice.

**Rollback scope.** `ainative update rollback` reverses the update transaction:
files it replaced come back from the backup, files it *created* are removed, and
the install state saved before the commit is put back. It works while that
transaction is still retained (the last 5), and it is derived from the journal
itself rather than from a second record beside it — so there is no window in
which an update has been applied and cannot be reversed.

It cannot restore a Python package installed elsewhere on the machine and does
not claim to; reinstall that with your package manager. It also leaves any
`<name>.new` file a conflict produced: those are yours to compare and delete.

### Two update surfaces, deliberately

| | What it updates | Mechanism |
|---|---|---|
| `scripts/stack-upgrade.sh` | the shared git **clone** | `git pull --ff-only` |
| `ainative update` | one **project's** install | ownership, digests, transaction, rollback |

If you consume the stack by *reference* (`@AGENTS.md`, symlinked skills), the
clone upgrade is all you need. If you *installed* into a project, `ainative
update` is the one that updates it. There is no second project updater.

---

## 9. Legacy installs

A project installed before the lifecycle existed has real managed files and no
state. It is detected by its markers (`tools/ai_docs/generate_all.py`,
`.claude/skills`, `.agents/skills`, `.stack-lock.json`) and adopted on the next
`ainative init`:

```
Existing AI Native installation detected (24 files).
Adopting managed components without overwriting user files.
```

Adoption is one-way conservative:

* digest matches a file the distribution ships → adopted as managed, ours to
  update and to remove;
* anything else → recorded as `MANAGED_MUTABLE` with `created_by_ainative =
  false`, which means it is tracked but never replaced and never removed.

Adoption makes a file *trackable*. It never makes it *ours*.

---

## 10. Doctor and repair

`doctor` reads and never writes. `repair` acts on what doctor reports.

| Status | Meaning | What `repair` does |
|---|---|---|
| `OK` | matches its install digest | nothing |
| `MISSING` | recorded but absent | reinstalls it |
| `USER_MODIFIED` | you edited it | **nothing** — reports and preserves |
| `CORRUPTED` | present, install digest unknown, or a path that no longer resolves | drops an unresolvable record; leaves the file |
| `ORPHANED` | component no longer declared | drops the record |
| `DUPLICATE` | two managed regions in one external file | reports |
| `INTERRUPTED` | a transaction never reached commit | rolls it back from its backup |

An unreadable `state.json` cannot be repaired, only set aside: `repair` moves it
to `state.json.corrupt-<timestamp>` with its bytes intact and tells you to run
`ainative init`, which then adopts the project the same way it adopts a legacy
install. Reconstructing ownership from a corrupt file would mean inventing
install digests — the exact guess that makes a later uninstall delete your work.

---

## 11. Security boundaries

**Assets.** User files · Verified evidence and trust state · external config
files · the update source · the filesystem boundary of the project root.

**Threats and what answers them.**

| Threat | Mechanism |
|---|---|
| Malicious manifest path (`../`, absolute, drive, UNC, NUL) | `paths.validate_relative` refuses at manifest load and again per operation |
| Symlink / junction escape | every path component is checked before a write or delete; a link out of the root is `PATH_ESCAPE` |
| Case-fold collision | two destinations sharing a case-folded key are refused at load |
| Tampered install state | a path that no longer resolves inside the project is refused, then dropped by `repair`; a tampered digest makes the file `USER_MODIFIED`, which is never deleted |
| Corrupt install state | quarantined, never guessed at |
| User edits overwritten | digest comparison before every replace; `MANAGED_MUTABLE` conflicts get `.new` |
| Partial operation | backup-first, commit-state-last, journal, `repair` |
| Stale lock | reclaimed only when the owner is provably dead; otherwise reported |
| Network failure / timeout | bounded timeout, `OFFLINE` is not fatal, cache serves the answer |
| Tampered download | SHA-256 verified before any write |
| Archive path traversal / bomb | entry names validated, entry count and expanded size bounded, extraction is manual per entry |
| Compromised release source | **not covered** — stated, not implied |

**Not in scope.** Release signing, a trusted-publisher model, and anything that
would let the lifecycle layer assert authority over Verified state.

---

## 12. Data retention

| Operation | Managed unchanged | Managed user-modified | `USER_DATA` (vault, memory, config) | Verified history | External config |
|---|---|---|---|---|---|
| `profile switch verified` | kept | kept | kept | kept | region refreshed |
| `profile switch standard` | Verified integration removed | kept | kept | **kept (dormant)** | region refreshed |
| `update` | replaced | **kept**, `.new` written beside | kept | kept | region refreshed |
| `update rollback` | restored; files the update added are removed | **kept** — `.new` files stay | kept | kept | region restored |
| `repair` | restored if missing | **kept** | kept | kept | region restored |
| `uninstall` | removed | **kept** | kept | **kept** | region removed |
| `uninstall --purge` | removed | **kept** | **kept** unless it is a declared data root | **removed** | region removed |
| `profile purge verified` | kept | kept | kept | **removed** | kept |

Files the stack never wrote are in the "kept" column of every row.

---

## 13. Versions, and why there are several

| Number | Source of truth | Changes when |
|---|---|---|
| Stack release | `VERSION` | a release is cut |
| Update protocol | `release_v3.BUNDLE_PROTOCOL_VERSION` (the current line, 3; the legacy v2 path keeps `provider.UPDATE_PROTOCOL_VERSION = 2`) | the bundle format changes |
| Lifecycle state schema | `state.SCHEMA_VERSION` | `state.json`'s shape changes |
| Work Plane runtime | `ainative_workplane.__version__` | the verdict engine is released |
| Artifact schema | `contracts.SUPPORTED_SCHEMA_VERSIONS` | a Work Plane artifact changes shape |

`ainative --version` prints them separately. They are compared with SemVer
rules, never as strings: `"1.10.0" > "1.9.0"` is false as text and true as a
version, and an updater that gets that wrong offers a downgrade as an upgrade.
A value that is not SemVer is refused rather than ordered as text.

---

## 14. Supported Python

| Surface | Supported | Tested in CI |
|---|---|---|
| Lifecycle CLI (`ainative`) | 3.11+ | 3.11, 3.13 on Linux / Windows / macOS |
| Verified Work Plane runtime | 3.11+ | 3.11 on Linux / Windows |
| AI-docs tooling installed into a project | 3.8+ | 3.9, 3.11, 3.13 (3.8 best-effort) |

The bootstrap wrappers gate on 3.11 for the CLI, and re-check the answer
`find_python.sh` gives them, because that helper was written for the 3.8+
tooling it installs.

---

## 15. Errors and exit codes

| Exit | Meaning |
|---|---|
| `0` | success |
| `1` | the operation ran and did not succeed, or the state is unhealthy |
| `2` | the request or configuration is invalid |
| `3` | recovery required — an interrupted transaction must be repaired first |

Stable error codes: `PROFILE_INVALID` · `COMPONENT_UNKNOWN` · `MANIFEST_INVALID`
· `DISTRIBUTION_SOURCE_UNAVAILABLE` · `PROJECT_ROOT_INVALID` ·
`CONFIRMATION_REQUIRED` · `PATH_ESCAPE` · `INSTALL_STATE_CORRUPTED` ·
`NOT_INSTALLED` · `USER_MODIFIED_CONFLICT` · `TRANSACTION_IN_PROGRESS` ·
`RECOVERY_REQUIRED` · `LOCK_HELD` · `UPDATE_UNAVAILABLE` · `UPDATE_CHECK_FAILED`
· `UPDATE_INTEGRITY_FAILED` · `UPDATE_INTEGRITY_METADATA_MISSING` ·
`UPDATE_VERSION_MISMATCH` · `CLI_UPDATE_REQUIRED` · `ROLLBACK_UNAVAILABLE` · `APPLY_FAILED`.

The CLI prints `refused: <CODE>: <message>` on stderr — never a traceback — and
`--json` emits `{"error": ..., "message": ..., "detail": {...}}`.

The Verified Work Plane's own exit codes are unchanged and are not
reinterpreted by the dispatcher.

---

## 16. Where things live

```
<project>/
├── AGENTS.md                          MANAGED_MUTABLE
├── conventions.json                   MANAGED_MUTABLE
├── .gitignore                         EXTERNAL_CONFIG (one region)
├── tools/ai_docs/                     MANAGED_IMMUTABLE
│   └── config.sh                      USER_DATA (never overwritten)
├── .claude/skills/                    MANAGED_IMMUTABLE
├── .claude/settings.json              EXTERNAL_CONFIG (one owned hook entry)
├── .agents/skills/                    MANAGED_IMMUTABLE
└── .ai-native/
    ├── templates/                     MANAGED_IMMUTABLE
    ├── docs/                          MANAGED_IMMUTABLE (verified)
    ├── trust/  work/  runs/           USER_DATA — the audit trail
    └── lifecycle/
        ├── state.json                 what is installed, and its digests
        ├── verified.json              activation record — never an authority fact
        ├── transactions/<id>.json     the journal
        ├── backups/<id>/              transaction-scoped, last 5 retained
        ├── update-cache.json          the cached check
        └── lifecycle.lock             held only during a mutation
```

---

## 17. The machine surface (global integration)

`ainative init` is per project. Installing the shared method, the skills and
the harness hooks into a *machine* is a different surface, owned by
`scripts/install_agents.py` from a stack checkout:

```bash
python scripts/install_agents.py                 # install or update (idempotent)
python scripts/install_agents.py --check         # verify what exists
python scripts/install_agents.py --dry-run       # preview
python scripts/install_agents.py --uninstall [--dry-run]
```

Every run records what it wrote in `~/.ai-native/machine.json`: each link with
its source, each managed block with its markers and preamble, each rendered
file with its digest. The uninstall reverses exactly that record —
links/junctions are removed and never followed, a rendered file is removed only
while its bytes match the recorded digest, a block is removed only while its
markers are present — and everything else (user skills, user agents, user
edits) is preserved and reported. `ainative doctor` reads the manifest to
report whether machine integration is present.

The machine surface has no project ownership state and no transaction journal;
re-running the installer *is* the update path.


## 18. Features (project-scope capabilities)

A profile is a governance level; a feature is an optional project-scope
capability. They are independent (ADR-0017): a `verified` project can be
Generic Git, and a `standard` project can work with GitLab.

```bash
ainative feature status
ainative feature enable forge-gitlab
ainative feature disable forge-gitlab
ainative feature switch forge-gitlab    # one transaction: disable + enable
ainative feature switch none            # Generic Git: no work forge
```

At most one **work forge** may be active. `forge-github` (the default) conflicts
with `forge-gitlab`; enabling a conflicting feature refuses with the remedy
(`feature switch`), and a state that names two work forges refuses as
`STATE_CONFLICTING_WORK_FORGE_FEATURES` rather than picking one.

State schema V2 records `active_features`. A V1 state has no such field and
projects to `forge-github` — the compatibility default, read-only. The
migration happens inside the next mutation, state-last like every other state
write, and plans no file change of its own: a previously managed file that is
already absent stays absent. Only an explicit feature transition seeds files.

Feature files follow the same ownership rules as everything else: enabling
seeds absent files, disabling removes only unchanged files and preserves files
the user modified, and re-enabling never overwrites a user file. One difference
from profile components is deliberate: ordinary `init`/`update` maintenance
never re-seeds an absent feature file — a file you removed stays removed until
a feature transition puts it back.
