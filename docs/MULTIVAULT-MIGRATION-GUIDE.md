> Nominal workflow is CLI-first: `ainative multivault bind`, `doctor`, `context`,
> `exec`, `sync`. The internal APIs shown later in this guide
> (`ainative.multivault.identity`, `AuthorityStore(...)`) are advanced/operator
> troubleshooting paths, not the nominal workflow.

# Multi-Vault Migration Guide

Existing installations start as PERSONAL + GUARDED. Classification never
upgrades automatically and no namespace is ever auto-loaded after a mismatch.

## Steps

1. `doctor` on the checkout to see current bindings and repository state.
2. Identify the vault (logical id, canonical root, device/file identity) and
   the checkout (worktree, git-dir/common-dir) with `ainative.multivault.identity`.
3. Write the binding into the operator authority store (trusted, outside the
   repository). A workspace file alone never authorizes anything.
4. Set the classification explicitly (PERSONAL/TEAM/CONFIDENTIAL/CRITICAL).
   Repository content can never raise it.
5. Qualify the harness/provider tuple with MV-00 probe evidence before any
   sensitive use; without evidence, sensitive admission stays DENY.
6. Migrate persistent state explicitly: a namespace mismatch REFUSEs; use
   `plan_migration` plus an operator approval reference - never auto-load.

## Never

- Share a REST API key between vaults or vault copies; regenerate after cloning
  `.obsidian` (see README: one Local REST API port per vault).
- Treat GUARDED as ENFORCED: GUARDED is not a hostile same-user boundary.
- Auto-promote GUARDED state to ENFORCED-*: exact-match only.

## Rollback

Authority-store writes keep the previous generation in `<store>.bak`;
`AuthorityStore.restore_from_backup()` recovers it atomically. Quarantine, do
not delete, state produced under a different namespace until an explicit
migration decision is recorded.
