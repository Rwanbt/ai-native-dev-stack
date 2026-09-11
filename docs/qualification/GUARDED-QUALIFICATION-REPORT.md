# GUARDED qualification report — Multi-Vault V1

Status: **NOT QUALIFIED** (implementation complete; qualification blocked on MV-00).

## What is qualified by this report

Nothing. No platform + harness + provider + plugin tuple has probe-backed
evidence (MV-00.2 semantic egress `UNKNOWN`, MV-00.4 harness autoload
`disable_control = UNKNOWN`, no model-egress or containment probe). A
qualification is tuple-specific; none exists today.

## What is demonstrated (executed, not claimed)

`python -m unittest tests.test_multivault_qualification` (7 tests, green):

| Scenario | Personal | Company A | Company B | Result |
|---|---|---|---|---|
| Memory namespace isolation | own | REFUSED from Personal | REFUSED from Personal/A | PASS |
| Declaration expansion (CRITICAL vs PERSONAL binding) | n/a | DENIED | n/a | PASS |
| Cross-domain declaration (Personal -> Company A store) | DENIED | n/a | n/a | PASS |
| MCP foreign caller / cross-domain handle / path escape | n/a | DENIED | handle DENIED | PASS |
| Push capability cross-domain / replay | n/a | DENIED | DENIED | PASS |
| Autoload admission without probe evidence | n/a | DENIED | n/a | PASS |
| Semantic admission without qualified profile | n/a | DENIED | n/a | PASS |
| Launcher loss (revoke_all) | n/a | handle DENIED | n/a | PASS |
| Audit records (metadata only) | PASS | PASS | PASS | PASS |

Cumulative Multi-Vault suite: 176 tests before this item (177+ with it).

## What would change this report

1. MV-00 probes per tuple (platform, harness, provider, plugin versions).
2. A qualified model-egress + containment tuple admitted through `capability.py`.
3. Canary baseline clean for the tuple (MV-01 surfaces).
4. Then, and only then, a tuple-specific line may be added here:
   `Windows 11 + <harness X.Y> + <provider Z> -> GUARDED QUALIFIED`.

Until that evidence exists, every sensitive admission path in this codebase
denies by construction.