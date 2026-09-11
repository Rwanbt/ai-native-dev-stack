# MV-00.2 — Smart Connections egress report

## Executed evidence

```text
python scripts/mv00/semantic_egress.py --vault-root D:\Documents\Obsidian\IA_Dev_Brain
```

The probe reads only plugin metadata and setting names. It does not emit setting values,
vault content, embeddings, network payloads, or credentials.

## Observed tuple

| Property | Observation |
|---|---|
| Plugin | Smart Connections |
| Version | 4.7.2 |
| Enabled | yes |
| Observable setting keys | `installed_at`, `last_version` |
| Runtime egress observation | none |

## Result

```text
semantic_background_egress = UNKNOWN
CONFIDENTIAL/CRITICAL semantic capability = unavailable
```

Installation and activation do not establish whether startup indexing, file-change
indexing, provider routing, endpoint changes, or background jobs cause egress. A future
qualified tuple needs a version-specific runtime observer before this state can change.
