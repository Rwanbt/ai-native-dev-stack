# Multi-Vault Troubleshooting

All sensitive decisions fail closed: DENY, REFUSE or INCOMPLETE are the safe
outcomes. Never bypass them to "make it work".

## Push and fetch codes

| Code | Cause | Action |
|---|---|---|
| AINATIVE_DIRECT_PUSH_DENIED | push without a governed capability (forged marker) | use the governed engine |
| AINATIVE_PUSH_CAPABILITY_EXPIRED / REPLAYED | capability out of time or reused | re-run the governed push once |
| AINATIVE_PUSH_CAPABILITY_MISMATCH / REFS_MISMATCH | stdin refs or intent fields differ | rebuild the PushIntent from the actual ref transaction |
| AINATIVE_PUSH_DOMAIN_MISMATCH / CHECKOUT_MISMATCH | capability from another domain/checkout | use the correct domain authority |
| AINATIVE_PUSH_LOCK_HELD | another governed push is in progress | wait; if stale, inspect the common git dir lock file |
| AINATIVE_PUSH_SCAN_LEAK / SCAN_INCOMPLETE | candidate scan found policy findings or could not complete | remove the finding or investigate; INCOMPLETE means deny |
| AINATIVE_FORCE_PUSH_DENIED / REF_DELETION_DENIED | force or delete refspec | explicit trusted policy + interactive approval |
| AINATIVE_FETCH/PUSH_DESTINATION_DENIED | remote identity/transport mismatch | fix the approved declaration or the repository remote |
| AINATIVE_SECONDARY_GIT_NETWORK_DENIED | promisor/partial configuration | remove the configuration; lazy fetch stays denied |
| AINATIVE_LFS_NETWORK_DENIED | LFS configuration or .lfsconfig | sensitive V1 never permits LFS network |
| AINATIVE_FETCH_FAILED / PUSH_FAILED | Git invocation failed | read the reported Git stderr line |

## Other failures

- `AuthorityStoreCorruptError`: the authority store is unreadable or has an
  unsupported schema; restore from `.bak` or rebuild with operator approval.
- Doctor shows UNKNOWN/FAIL: that is fail closed, not a bug. Provide the
  missing evidence (bindings, hooks path, probe results).
- REST answers 401 with your key: the endpoint belongs to another vault; give
  each vault its own port (README section) and re-verify with status-only
  probes (200 for the owner, 401 for others).
- Semantic observer unavailable/unreadable: the governed session must be
  revoked; there is no "treat as safe" path.
