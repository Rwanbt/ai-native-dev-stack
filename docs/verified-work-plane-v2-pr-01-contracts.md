# Verified Work Plane V2 — PR-01 Contract Boundary

> **Historical packet.** This is the PR-01 contract report, kept as the record of a decision point. It describes the branch as it was at that gate, not as it is now. For current behaviour read [ARCHITECTURE.md](ARCHITECTURE.md) and the tests.

PR-01 provides only deterministic, versioned data contracts in
`ainative_workplane`. It has no controller, CLI, repository collector, command
runner, freshness evaluator, convergence engine, or provider integration.

Normative objects use NFC-normalized UTF-8 JSON, lexicographically sorted object
keys, `,` / `:` separators, and no floats. Their digest is SHA-256 of those exact
bytes. Schema versions are independent from both the runtime and root `VERSION`.
An unsupported required schema is represented by `UNSUPPORTED_SCHEMA_VERSION`; no
automatic migration exists.

Repository paths are Unicode NFC, repository-relative, slash-separated, and may
not contain an empty, `.` or `..` component. A leading-dot filename is legal.
Windows separators normalize to `/`; case-fold collisions are rejected. Symlink
containment needs filesystem evidence and therefore belongs to later collection
logic rather than this data-only PR.

The validation shapes deliberately make the structural gaps required by
[[verified-work-plane-v2-contract-sketches|PR-00]] observable in PR-03. In
particular, requirements reference ACs, ACs reference verification specifications,
and non-direct specifications require covered paths or structured dependencies.

The trusted computing base includes this runtime package, its validator,
canonical serializer, digest implementation, later approval-predicate evaluator,
and later deterministic convergence implementation. V2 does not claim to prove
the integrity of that computing base from inside itself.
