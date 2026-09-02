# Verified Work Plane V2 — Contract Sketches

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

