---
name: debt-architecture
description: Detect architecture-level technical debt: coupling, cycles, boundary violations, layer leaks. Outputs findings conforming to the debt-finding schema.
license: MIT
---

# Skill: debt-architecture

## When to use me
- Audit of a repo's architecture (coupling, dependencies between modules)
- After a major refactor (verify boundaries are still respected)
- When manual code review flagged "this is too coupled" without a tool to validate
- Before merging a PR that adds new modules or imports

## Method (MANDATORY)

### Step 1: Detect language and project structure
Same as `debt-scan` — use `LANG_MAP` from `tools/scan_code.py` to identify primary language.

### Step 2: Run architecture scanners
For each language, run the appropriate architecture scanner:

| Language | Tool | Detects |
|----------|------|----------|
| Python | `pydeps` (or custom AST walker) | Circular imports, fan-out, fan-in |
| Rust | `cargo geiger` + custom cycle detector | Circular crate deps, unsafe FFI |
| TypeScript/JS | `dependency-cruiser` (already used) | Layer violations, circular imports, reach |
| Java | `jdeps` + `maven-dependency-plugin` | Cycle detection, layer violations |
| Go | `go list -f '{{.ImportPath}}'` + custom cycle detector | Circular package deps |

If a tool is not available, fall back to the custom AST walker (see `tools/scan_architecture.py`).

### Step 3: Classify findings
Architecture findings are typed differently from code findings:
- **Circular dependency** (category: `architecture`, subcategory: `circular_dependency`)
- **High coupling** (category: `architecture`, subcategory: `high_coupling`)
- **Boundary violation** (category: `architecture`, subcategory: `boundary_violation`)
- **Layer leak** (category: `architecture`, subcategory: `layer_leak`)
- **God module** (category: `architecture`, subcategory: `god_module`)

### Step 4: Critic Engine (MANDATORY)
Same as `debt-scan` — invoke `skills/critic/SKILL.md` on the complete list.

### Step 5: KG persistence (V2)
Each finding creates a `Debt` node in the KG with an `affects` edge to the affected `Component` nodes (per ADR-0023).

### Step 6: Update the debt registry
New architecture findings are added to the registry with:
- Owner: who needs to fix
- Severity: based on number of modules affected
- Status: open (initial)

## What I produce
- `.debt-architecture.json` : findings + critic report (V1 format)
- KG nodes (V2) : Debt + Component + Edge
- Updated debt-registry.json
- `report-architecture.md` : human-readable summary

## Tools used
- `tools/scan_architecture.py` : orchestrates the scanners + custom AST walker
- `kg_store.py` (Layer 0) : persistence
- `skills/critic/SKILL.md` : mandatory critic

## Non-NEGOTIABLE rules

1. **Evidence required** : every architecture finding MUST have a concrete cycle path or coupling metric
2. **Confidence threshold** : same as code findings (0.6 minimum)
3. **Critic mandatory** : no architecture finding without critic validation
4. **KG persistence** : all findings must be in the KG, not just in JSON
5. **V1 compatibility** : the `.debt-architecture.json` file is also written for V1 consumers
