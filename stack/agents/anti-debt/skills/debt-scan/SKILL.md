---
name: debt-scan
description: Scan a codebase to detect technical debt (code, security, dependencies, tests). Orchestrate deterministic tools + LLM. Produce a `.debt-scan.json` file conforming to the schema.
license: MIT
---

# Skill: debt-scan

## When to use me
- Initial or periodic audit of a repo
- Before a major refactor
- Post-MVP to trace the debt introduced
- In CI on every PR (lightweight mode)

## Method (MANDATORY — no shortcuts)

### Step 1: Deterministic tools first
Run in order:
1. `tools/scan_code.py` (ruff / clippy / eslint / golangci-lint wrapper depending on language)
2. `tools/scan_security.py` (trufflehog + osv-scanner + gitleaks)
3. `tools/scan_deps.py` (dependency-cruiser + cargo audit / npm audit / pip-audit)
4. Tests: coverage + flaky detection

Each tool produces structured JSON. **No debt can be declared without going through a tool OR without explicit LLM proof.**

### Step 2: LLM reasoning (complement)
For findings not covered by tools (architecture, semantic debt):
- Invoke the LLM with bounded context
- Each LLM finding MUST have `confidence` + `evidence`
- The Critic Engine challenges in parallel

### Step 3: Critic Engine (MANDATORY)
Invoke `skills/critic/SKILL.md` on the complete list.
Findings rejected by the Critic → excluded from the final report.

### Step 4: Scoring
For each validated finding:
```
score = (impact × urgency × confidence) / effort_days
```
- impact/urgency estimated via heuristics + LLM (calibration V2)
- effort: S=1, M=3, L=8, XL=20 (person-days)

### Step 5: History
Compare to previous scans in `.debt-history.json`:
- Findings resolved (since last scan)
- Findings regressed (came back)
- Total debt delta

### Step 6: Scope Completeness Check
Explicitly list:
- Categories scanned vs taxonomy
- Findings omitted and why
- Assumptions

## What I produce
- `.debt-scan.json` : validated findings + score + critic report
- `.debt-history.json` : updated with this scan
- `report.md` : executive summary

## Tools used
- `tools/run_all.sh` : orchestrator
- Read, Grep, Glob, Bash (layer 3 — always available)
- Vendor adapters (layer 4) optional
