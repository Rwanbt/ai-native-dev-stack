# Knowledge Operations — runbook for working state, checkpoints and hooks

Status: Phase K2. Parents: ADR-0011, `docs/KNOWLEDGE-ARCHITECTURE.md`.
All commands below are script-safe: mutations take `--dry-run`,
confirmations take `--yes`, machine output takes `--json`.

## 1. Daily use

```text
ainative context save --task "..." --next-action "..." --touch <path> --blocker "..."
ainative context status
ainative knowledge candidates
ainative knowledge status
```

`context save` merges: scalars replace when the flag is given, repeatable
flags (`--touch --hypothesis --finding --question --test --blocker
--candidate`) append deduplicated. Bounds are enforced
(`MAX_LIST_ITEMS 200`, `MAX_TEXT_CHARS 4000`, `MAX_ITEM_CHARS 1000`);
overflow is refused with `KNOWLEDGE_MALFORMED`, never truncated silently.

## 2. Compaction (context reset without losing the thread)

```text
ainative context checkpoint --reason precompact     # freeze: state + repo head + pending ids
... compaction happens ...
ainative context restore <checkpoint_id>            # bring it back
```

`restore` compares the frozen repository head with the current one:

| Outcome | Meaning | Action |
|---|---|---|
| `restored` | same head (or no head recorded) | continue |
| `restore_requires_reconciliation` | head moved, or current head unreadable | re-verify files moved, tests, blockers before continuing |

Checkpoints keep the last 10 and drop entries older than 30 days
(`prune_checkpoints`, enforced on every checkpoint). A checkpoint freezes
operational state only — task, hypotheses, blockers, next action, pending
candidate ids — never raw chain-of-thought.

## 3. Crash recovery matrix

| `load` outcome | Disk state | Meaning | Action |
|---|---|---|---|
| `empty` | no files | nothing saved yet | `save` to start |
| `current` | valid working file | normal | continue |
| `expired` | past `expires_at` | TTL elapsed, content returned anyway | re-validate, then `save` |
| `recovered` | current corrupt, backup valid | crash or partial write | review, then `save` to persist |
| `KNOWLEDGE_STORE_CORRUPTED` | both unreadable | fail closed | rebuild state by hand; nothing is fabricated |

`load` never rewrites: recovery is reported, persistence is an explicit
`save`. Every write is temp-write plus atomic replace; the previous good
copy becomes the backup before the new bytes land.

## 4. Promoting a candidate (preview-first, human-approved)

> QUARANTINE: same status as above. Preview-first and base digests make this a careful local patch tool, not production-trust-qualified promotion.

```text
ainative knowledge transition <id> READY_FOR_PROMOTION --actor <triage-owner>
ainative knowledge promote <id> --operation ADD --dry-run
# read the diff preview, then:
ainative knowledge promote <id> --operation ADD \
    --approve "<reason>" --expect-base <base_digest> --actor <name>
```

Rules: every canonical target needs `--approve` today (AGENTS.md, ADRs,
failure patterns, AI_CONTEXT — see `policy.py`; relaxing one class takes
a new ADR). `--expect-base` is mandatory: a target that moved since the
preview aborts with `STALE_BASE` before a byte is written. `MERGE`,
`REFINE` and `SUPERSEDE` additionally need `--anchor <exact-once-text>`;
an explicit `--target` disambiguates multi-file hints. `reject <id>`
refuses without writing. `reconcile <id>` heals a crash between the
file write and the audit (`healed-status`, `healed-audit`, `diverged`
needs a human, `consistent` otherwise).

## 5. Discarding state

```text
ainative context clear --dry-run    # preview
ainative context clear --yes        # discard working file, backup, checkpoints
```

Safe by plane: canonical Markdown, Vault notes, Git history, candidates
and audit events are untouched. Without `--yes` (and without `--dry-run`)
the command refuses with `KNOWLEDGE_CONFIRMATION_REQUIRED`.

## 6. Hook adapter contract (PreCompact, SessionStart, SessionEnd)

Hooks shell out to the CLI; the CLI is authoritative. Recommended wiring:

| Event | Command | On failure |
|---|---|---|
| PreCompact | `ainative context checkpoint --reason precompact --project <root>` | warn only, never block compaction |
| SessionStart | `ainative context status --project <root>` | warn only, continue without working state |
| SessionEnd | `ainative context checkpoint --reason session-end --project <root>` | warn only |

Rules: hooks parse `--json` output, never text. A hook MUST NOT promote,
merge or rewrite canonical files. A hook MUST NOT pass secrets on the
command line (capture-time secret detection would refuse them anyway).
Harness-specific scripts (`hooks/`, per-agent `hooks.json`) stay thin
wrappers around these commands; no lifecycle logic in the wrapper.

## 7. Retention and TTL

## 8. Observability (telemetry-free, local only)

Knowledge health (all `--json` scriptable):

```text
ainative knowledge status        # store state, counts by status, conflicting/promoted
ainative doctor --json           # .knowledge section: same report inside lifecycle diagnosis
ainative knowledge export        # full candidates plus audit dump (backup/rotate remedy)
```

Agent effectiveness signals (derived locally, never phoned home): repeated
corrections surface as DUPLICATE findings in `verify`/`consolidate`;
promotion rate, conflict counts and stale findings come from
`consolidate --json` plus `stale --json`; retrieval cost is reported per
bundle (`total_bytes`, `estimated_tokens`, `dropped`). Performance
guardrails live in `tests/test_knowledge_perf.py` — loose by design;
tighten only from measured distributions.

## 9. Migration and rollback

Adoption is additive: existing Vault notes, `AGENTS.md`, `AI_CONTEXT.md`
and session files are never reformatted or moved by any knowledge
command. Canonical promotion is recovered with Git (every promotion is
one minimal, attributed patch — `git log -S <candidate_id>` finds it).
Derived state needs no backup (recomputed on demand; `reset-derived`
plus `rebuild` prove it). Transient state is discarded with
`context clear --yes`. A full store refuses with `KNOWLEDGE_CONFLICT`
naming the remedy: `knowledge export` to a file, then rotate.

| Store | Bound | Enforced by |
|---|---|---|
| working lists | 200 items, 1000 chars/item, 4000 chars/text | `WorkingState.from_record` |
| checkpoints | last 10, max 30 days | `prune_checkpoints` on every checkpoint |
| candidates | 1000 records | `store.append` refuses past the bound |
| audit events | 5000 events | `store.record_audit` refuses past the bound |
| working TTL | optional `--ttl` seconds | `load` reports `expired` |

Canonical knowledge is never garbage-collected. Full stores refuse with
`KNOWLEDGE_CONFLICT` plus the remedy (consolidate or export first).