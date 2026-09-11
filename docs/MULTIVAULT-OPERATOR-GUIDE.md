> Status note: the current qualification is MULTI-VAULT GUARDED - PRODUCTION READY (A/B/C/D GUARDED QUALIFIED). See docs/qualification/MULTIVAULT-QUALIFICATION-REPORT-2026-09-11.md. ENFORCED is optional high-assurance hardening and is not required.

# Multi-Vault Operator Guide

Implementation status: cores are implemented and fail closed. No
platform/harness/provider tuple is qualified; CONFIDENTIAL/CRITICAL admission
is DENY everywhere. This guide describes what exists today, not a production
qualification.

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

Current state lives in `docs/spikes/multivault/CAPABILITY-MATRIX.json`; the
tuple-specific verdict is `docs/qualification/GUARDED-QUALIFICATION-REPORT.md`
(NOT QUALIFIED). ENFORCED-DIAGNOSTIC and ENFORCED-AUTHENTICATED are not
available.
