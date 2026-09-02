# ADR-0001: Keep Work Plane Authority Independent from Optional Providers

**Date:** 2026-09-02  
**Status:** Accepted for PR-00 baseline

## Context

The repository already installs AI assistance tooling, validates and synchronizes an
optional Obsidian vault, runs session hooks, and ships an independent anti-debt agent.
The V2 plan needs a portable Work Contract that survives harness changes and cannot have
its success criteria silently rewritten by the controlled implementation.

## Decision

The future V2 core owns Work Contracts, verification specifications, repository
snapshots, verification runs, and deterministic convergence. Vault, Graphify, ADR text,
Spec Kit, and anti-debt remain optional read-only providers. Plans are narrative unless
their obligations are promoted into structured normative artifacts.

The V2 runner will execute only registered `argv` commands. Its state mutation protocol
will use immutable revisions and a manifest written last.

V2 is a first-party Python package, `ainative_workplane`, invoked during development as
`python -m ainative_workplane`. Its own runtime/schema compatibility version is separate
from the existing stack root `VERSION`. The portable trust baseline is a Git-reviewed
commit plus recorded command-registry and policy digests; dirty or unapproved local
trust-base changes downgrade evidence to `local_untrusted`.

## Rejected alternatives

- Make Obsidian the Work Contract store: rejected because local vault availability and
  synchronization must not gate portable execution.
- Extend anti-debt into the convergence engine: rejected because debt assessment and
  declared-contract satisfaction are distinct questions.
- Treat plan or ADR prose as executable policy: rejected because it introduces
  ambiguous, agent-interpreted authority.

## Consequences

The core initially adds more structured artifacts than a prose checklist, but provides
reproducible authority. PR-01 must define the schemas and canonical serializer before
any controller or runner is implemented.
