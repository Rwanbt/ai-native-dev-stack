# MV-00.1 — REST feasibility report

## Scope

This report records a bounded local observation of the Obsidian Local REST API.
It does not use an API key, read vault content, or follow redirects.

## Executed evidence

Command:

```text
python scripts/mv00/rest_feasibility.py --output docs/spikes/multivault/REST-FEASIBILITY-REPORT.json
```

Observed on 2026-09-11:

| Endpoint | Result |
|---|---|
| `https://127.0.0.1:27124` | unreachable (`URLError`) |
| `http://127.0.0.1:27123` | unreachable (`URLError`) |

## Result

```text
REST_IDENTITY_BINDING = UNKNOWN
CONFIDENTIAL/CRITICAL REST capability = unavailable
```

Reachability alone would remain insufficient: this probe does not accept an endpoint as
bound to a vault without an independently observable, expected vault identity. A redirect
is recorded and denied rather than followed.

## Follow-up required for a qualified tuple

Run the probe with a named local endpoint and an expected logical vault identity after an
adapter exposes a trustworthy endpoint-to-vault correlation signal. Until then, the
runtime must keep REST unavailable for sensitive classifications, per ADR-0015.
