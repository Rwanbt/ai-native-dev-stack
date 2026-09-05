# Verified Work Plane V2 — Contract Sketches

> **STATUS: HISTORICAL QUALIFICATION RECORD** — retained for auditability.
> This document records the state of the Verified Work Plane work at the time
> it was written; it is not the current operational status. See
> [docs/VERIFIED-WORK-PLANE.md](VERIFIED-WORK-PLANE.md) for current state.

> **Historical packet.** This is the PR-01 contract sketches, kept as the record of a decision point. It describes the branch as it was at that gate, not as it is now. For current behaviour read [ARCHITECTURE.md](ARCHITECTURE.md) and the tests.

These sketches are PR-00 design input, not implemented schemas.

```json
{
  "schema_name": "work_manifest",
  "schema_version": 1,
  "work_uid": "work_<non-sequential-id>",
  "revision": 1,
  "artifacts": {
    "requirements": {"path": "revisions/1/requirements.json", "digest": "sha256:<digest>"}
  }
}
```

```json
{
  "snapshot_version": 1,
  "head_commit": "<sha>",
  "dirty": true,
  "scope": {"paths": ["src/example.py"]},
  "dependencies": ["pyproject.toml"],
  "content_digest": "sha256:<digest>",
  "command_registry_digest": "sha256:<digest>",
  "policy_digest": "sha256:<digest>"
}
```

The manifest becomes authoritative only after PR-01 schema validation and PR-02 crash
tests. Display IDs are human labels derived from non-sequential machine UIDs; neither a
local counter nor a plan heading is a normative identifier.

