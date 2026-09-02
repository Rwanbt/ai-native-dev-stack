# Verified Work Plane V2 — H0 Inventory

> **Historical packet.** This is the H0 inventory, kept as the record of a decision point. It describes the branch as it was at that gate, not as it is now. For current behaviour read [ARCHITECTURE.md](ARCHITECTURE.md) and the tests.

**Status:** Verified baseline inventory  
**Scope:** `spec` at `7c034db`  
**Method:** Direct read of all 11 V2 runtime modules, 10 V2 test modules, and
the six V2 authority documents named by the production-hardening plan.

## Ownership matrix

| Component | Owner / writer | Readers | Normative | Trusted / persistent | Schema / current tests | Verified gap |
| --- | --- | --- | --- | --- | --- | --- |
| `contracts.py` | Contract validators; no writer | Controller and callers | Yes | In-memory validation only | 12 schema identities; contract tests | `verification_run` shape is richer than the runtime evidence shape. |
| `controller.py` | `WorkController` | CLI and callers | Yes | Revisions and manifest are persistent | Work-manifest validation; controller tests | Arbitrary maps remain acceptable, mutation replaces the complete artifact set, and lock/staging recovery is not crash-safe. |
| `snapshot.py` | Snapshot collector | Future runner/convergence | Intended yes | Not persisted | Path/symlink/collision tests | Produces only a path-to-digest map, not a `repository_snapshot` artifact. |
| `runner.py` | `VerificationRunner` | Convergence callers | Evidence producer | Optional JSON files | Runner tests | `RunResult` does not validate as `verification_run`; default provenance is `GIT_REVIEWED`; output is accumulated unbounded before its limit is checked. |
| `traceability.py` | Deterministic graph builder | Convergence | Yes | In-memory | Structural tests | Does not validate complete verification scope or every required relation from the hardening contract. |
| `convergence.py` | Deterministic verdict function | CLI/callers | Yes | Optional JSONL history | Convergence tests | Accepts arbitrary run mappings; does not bind evidence, trust, scope, or current snapshot. Public `BLOCKED` conflicts with the frozen production verdict set. |
| `cli.py` | CLI facade | Developers | No | None | CLI test | Exposes create/validate/update only; no package-level verification/convergence workflow. |
| `integrations.py` | Read-only adapters | Optional callers | No | None | Integration test | Correctly non-authoritative, but only shape adapters. |
| `metrics.py` | Pilot metrics writer | Pilot/report callers | No | Optional JSON | Metrics test | No production performance or memory measurements. |
| Authority docs | PR-00 documents | Humans and agents | Architecture authority | Repository Markdown | Existing regressions | Some claims describe planned controls rather than runtime behaviour. |

## Confirmed contradictions to resolve sequentially

### H1 — unified evidence model

- `contracts.py` requires a `verification_run` to bind work, contract digest,
  verification specification, approval root, repository snapshot, registry,
  policy, producer, timestamps, substance and provenance.
- `runner.py` writes only `uid`, command, status, exit code, complete stdout and
  stderr, duration, and a provenance string.
- `convergence.py` accepts any mapping containing `status`. Therefore a forged
  `{"uid": "x", "status": "PASS"}` can converge when the graph has no gaps.

### H2 — trust and root of trust

- `VerificationRunner.__init__` defaults provenance to `GIT_REVIEWED` without
  evaluating an approval root, Git state, policy, or registry authority.
- Contract validation constrains the *shape* of roots, policies, waivers, and
  human approvals but does not evaluate an authorization chain.

### H3/H4 — traceability and freshness

- Traceability establishes basic requirement-to-acceptance, acceptance-to-spec,
  and requirement-to-task links, but does not evaluate relationship coverage.
- Freshness is caller-supplied strings; no evaluator compares current contracts,
  snapshots, scopes, dependencies, policy, registry, or approval root.
- Snapshot safety primitives exist, but there is no persisted snapshot object.

### H5 — runner hardening

- `argv` plus `shell=False`, timeout, and a basic redactor already exist.
- `subprocess.run(capture_output=True)` retains output until process completion;
  it cannot enforce a bounded-memory output policy or terminate a process tree on
  overflow.
- Non-empty output is the only current substance signal.

### H6/H7 — convergence and controller durability

- Current verdicts are `CONVERGED`, `BLOCKED`, and `INVALID`; the production
  contract requires frozen external verdicts `CONVERGED`, `NOT_CONVERGED`, and
  `INVALID`, with `INTERNAL_ERROR` reserved for engine failure.
- The controller retains immutable revisions and manifest-last replacement, but
  has a file-exists lock without owner metadata or stale-lock policy. Its recovery
  deletes all staging directories and its mutation API replaces, rather than
  explicitly patches, the artifact set.

## H0 gate decision

The production-hardening architecture is internally consistent with the existing
PR-00 authority documents. The implementation does not satisfy its production
guarantees, so the next permissible change is H1: replace the parallel runtime
and contract evidence models with one validated, bound evidence record.

## Deferred until later gates

- H2 authorization-chain evaluation;
- H3 scope-relationship validation;
- H4 snapshot/freshness evaluation;
- H5 streaming execution and substance adapters;
- H6 convergence selection;
- H7 controller recovery;
- H8-H13 package, adversarial, historical, and real-pilot evidence.
