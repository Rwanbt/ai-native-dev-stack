---
name: debt-prevention
description: Generate preventive rules (linters, tests, CI checks) from detected findings. Stops the same pattern from re-appearing after a fix.
license: MIT
---

# Skill: debt-prevention

## When to use me
- After a fix is applied (`debt-verify` reports success)
- When a finding pattern recurs 3+ times across the repo
- When 3+ findings share the same subcategory
- Before major refactors (establish guardrails first)

## Method (MANDATORY)

### Step 1: Analyze findings
Read `.debt-scan.json` (V1) or query the KG (V2). Find:
- Patterns: same subcategory appearing 3+ times
- Hot zones: same file with 3+ findings
- Recurring bugs: same finding id appearing in multiple scans

### Step 2: Generate preventive rules per language
For each pattern, generate the appropriate rule:

| Pattern | Language | Rule type | Tool |
|---------|----------|-----------|------|
| `code.complexity` | Python | `ruff` config rule | `ruff` |
| `code.complexity` | Rust | `clippy.toml` config | `cargo clippy` |
| `code.complexity` | TS/JS | `.eslintrc` rule | `eslint` |
| `security.secrets_in_code` | Any | `gitleaks` config | `gitleaks` |
| `security.known_vulns` | Any | `dependabot.yml` | GitHub |
| `dependencies.circular` | Python | `pydeps` config | `pydeps` |
| `dependencies.circular` | TS/JS | `dependency-cruiser` config | `depcruise` |
| `tests.coverage_gaps` | Any | CI coverage threshold | `coverage.py`, `tarpaulin`, `jest` |

### Step 3: Generate tests
For each pattern, generate a regression test that fails if the pattern re-appears.

### Step 4: Generate CI checks
For each rule, generate a CI step that runs the tool on every PR.

### Step 5: Update KG
Each preventive rule becomes a `Convention` node in the KG, with `blocks` edge to the `Component` it protects.

### Step 6: Critic Engine
Critic reviews generated rules for:
- False positives (rule too strict, blocks legitimate code)
- Maintenance burden (rule too noisy)
- Compatibility (rule conflicts with existing config)

## What I produce
- `prevention-rules/<pattern>.toml|yaml|json` : config files for linters
- `prevention-tests/test_<pattern>.py` : regression tests
- `.github/workflows/prevention-<pattern>.yml` : CI steps
- KG nodes (Convention + edges)
- `prevention-report.md` : summary of generated rules + their rationale

## Tools used
- `tools/prevent_finding.py` : orchestrator
- `kg_store.py` (Layer 0) : persistence
- `kg_sync.py` (Layer 0) : vault projection
- `skills/critic/SKILL.md` : mandatory

## Non-NEGOTIABLE rules

1. **No rule without a finding** : every preventive rule must trace back to a specific finding
2. **No noisy rules** : if a rule fires > 5 times on legitimate code, it must be tuned
3. **Always with test** : every rule has a corresponding regression test
4. **Critic mandatory** : rules must pass the critic before being deployed
5. **KG persistence** : every rule is a `Convention` node
6. **Reversible** : every rule can be disabled via a kill switch in case of false positive
