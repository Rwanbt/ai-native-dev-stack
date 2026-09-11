# MV-01 baseline inventory

## Confirmed global surfaces

`hooks/lib/obsidian_client.js` reads `OBSIDIAN_API_KEY` and
`OBSIDIAN_API_URL` from the process environment. The values are global and
carry neither a security-domain binding nor a vault identity binding.

## Classification

```text
CONFIDENTIAL/CRITICAL hook REST access = unavailable
remediation owner = MV-10 Obsidian client refactor
```

The MV-01 cross-domain canary denies mismatched source/request domains before
any future adapter reaches I/O. This is a baseline guard, not a claim that the
legacy global client is governed.
