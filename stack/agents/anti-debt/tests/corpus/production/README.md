# Production Eval Datasets

Datasets mined from real `.debt-history.json` files via `tools/production_mining.py`.

## Structure

Each file is a timestamped JSON with:
- `metadata`: generation info
- `stats`: distribution of labels, categories, severities, confidence buckets
- `examples`: array of `{input, expected_verdict, reason, provenance}`

## How labels are derived

Human overrides in `.debt-history.json` serve as ground truth:
- `accept_override` → the finding was correct (true positive)
- `reject_override` → the finding was wrong (false positive)
- `confirm` → the finding was verified correct (high-confidence TP)

## Usage

```bash
# Mine from a single project
python tools/production_mining.py --history /path/to/.debt-history.json --output tests/corpus/production/

# Mine from all projects in a directory
python tools/production_mining.py --history-dir D:/App/ --output tests/corpus/production/
```

## Versioning

Files are named `mined-YYYYMMDD.json`. Keep old versions for regression tracking.
Do not delete — the eval pipeline uses the latest file by default.
