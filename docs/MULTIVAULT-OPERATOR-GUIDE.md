> Status note: the current qualification is MULTI-VAULT GUARDED - PRODUCTION READY (A/B/C/D GUARDED QUALIFIED). See docs/qualification/MULTIVAULT-QUALIFICATION-REPORT-2026-09-11.md. ENFORCED is optional high-assurance hardening and is not required. Issue #122 is closed: `ainative multivault exec` and `ainative multivault sync` are available, and the clean-install wheel E2E exercises bind, doctor, context, exec and sync from the installed wheel.

# Multi-Vault Operator Guide

Implementation status: cores are implemented and fail closed. The current
qualification is MULTI-VAULT GUARDED - PRODUCTION READY (profiles A/B/C/D
GUARDED QUALIFIED); see docs/qualification/MULTIVAULT-QUALIFICATION-REPORT-2026-09-11.md.
ENFORCED (dedicated OS account, ACL boundary, external authenticator) is
optional high-assurance hardening, experimental and NOT QUALIFIED; it is not a
condition for GUARDED.

## Commands

- `python -m ainative.multivault audit-query <log.jsonl> [--domain X] [--decision Y] [--reason-code Z]`
  prints metadata-only audit records (JSON lines).
- `python -m ainative.multivault doctor --store <authority.json> --domain <id> [--repo .]`
  runs fail-closed checks (binding, repository, managed hooks path); UNKNOWN is
  never PASS and the exit code is non-zero unless every check is PASS.
- `python -m ainative.multivault context --store <authority.json> --domain <id>`
  fails closed without a binding; prints classification, vault/checkout,
  qualification (never a bare ENFORCED) and `supported: no` until probe
  evidence exists.

## Authority store

Trusted operator data, outside the repository:
`{"schema_version": 1, "bindings": {"<domain>": {"vault": ..., "checkout": ...,
"classification": ..., "roots": [...]}}}`. Writes are atomic and keep a `.bak`
generation; corruption raises `AuthorityStoreCorruptError` (fail closed).

## Admission map

| Module | Decides | Key rule |
|---|---|---|
| `binding.py` / `resolver.py` | workspace admission | repository cannot raise classification or roots |
| `admission.py` | repo autoload surfaces | probe-backed adapter required for TEAM+ |
| `semantic.py` | semantic providers | probe-qualified profile + approved egress digest |
| `persistence.py` | store namespaces | exact-match only; explicit migration |
| `mcp_adapter.py` | thin MCP operations | session capability + caller + response confinement |
| `push_guard.py` | governed pushes | single-use capability, all stdin refs must match |
| `transfer_engine.py` | fetch/push execution | destination/transport validated before network |

## Git transfers

The engine is the governed writer: positive Git environment, push lock held
through the transfer, candidate scan before push, force/deletion denied.
Sensitive secondary network (promisor/partial, LFS, submodule recursion) is
refused with stable codes.

## Qualification

Current state lives in `docs/spikes/multivault/CAPABILITY-MATRIX.json` under
`current_qualification`. The pre-qualification report
`docs/qualification/GUARDED-QUALIFICATION-REPORT.md` is SUPERSEDED and kept for
history only. ENFORCED-DIAGNOSTIC and ENFORCED-AUTHENTICATED are not available.

## Working procedure (real machine, step by step)

1. Install and initialize the stack (pinned release; see README for the current version):

   ```powershell
   pip install --upgrade "git+https://github.com/Rwanbt/ai-native-dev-stack.git@v2.4.2"
   ainative machine init      # installs the method and assets for every harness
   ainative machine doctor    # healthy, or exit 1 naming the failing asset
   ```

2. Bind one domain per (vault, checkout) pair. The authority store is trusted operator data,
   outside repositories and vaults (`~/.ai-native/multivault-authority.json`). It is
   machine-local: every participant binds on their own machine; it is never committed or shared.

   ```powershell
   ainative multivault bind --store "$env:USERPROFILE\.ai-native\multivault-authority.json" `
     --domain <domain> --vault-id <vault-id> --checkout-id <checkout-id> `
     --vault "<vault root>" --checkout "<git checkout>" `
     --classification <PERSONAL|TEAM|CONFIDENTIAL|CRITICAL>
   ```

   Rules: one domain per vault/checkout pair - never reuse a domain across vaults; the checkout
   must be a real Git repository (private for sensitive work, with `core.hooksPath` set so the
   `managed_hooks_path` check passes); vault and checkout stay separate trees.

3. Verify before working:

   ```powershell
   ainative multivault doctor --store <store> --domain <domain> --repo "<checkout>" --vault-root "<vault>"
   ainative multivault context --store <store> --domain <domain>
   ```

   `binding`, `checkout_identity`, `root_freshness`, `repository` and `managed_hooks_path` must
   be PASS. `canary` stays UNKNOWN (placeholder): the doctor exit code is non-zero until every
   check is PASS - that is fail-closed, not a bug. Moving or replacing a vault/checkout root
   invalidates the binding (`DENY_ROOT_STALE` / `DENY_CHECKOUT_STALE`): re-bind after the move.

4. Governed `exec` and `sync` (usage notes):
   - `exec`: place the approved command after the options **without** a `--` separator; with
     2.4.2 the separator is captured by argv and the spawn fails with a file-not-found error.
   - `sync`: the Git environment is positive-only (no ambient credentials or proxies). A fetch
     from a private remote without dedicated credential material is denied by design
     (`AINATIVE_FETCH_FAILED`); `file://` and public remotes work. Force pushes and ref
     deletions are denied; a push must target a ref inside the approved remote `allowed_refs`,
     with the refspec destination equal to the push intent `target_ref`.

5. Qualification remains MULTI-VAULT GUARDED. Never present it as ENFORCED; the same-OS-user
   boundary is outside GUARDED. Codes and remedies: `MULTIVAULT-TROUBLESHOOTING.md`. Migrating
   an existing setup: `MULTIVAULT-MIGRATION-GUIDE.md`.
