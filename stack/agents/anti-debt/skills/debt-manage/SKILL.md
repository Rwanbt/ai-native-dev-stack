---
name: debt-manage
description: CRUD operations on the Debt Registry. Manages the active list of accepted debts, decisions, and resolution status. Persists to the KG (Layer 0).
license: MIT
---

# Skill: debt-manage

## When to use me
- To register a new debt as "accepted" (deliberately not fixing it)
- To mark a debt as "in_progress" (work has started)
- To mark a debt as "resolved" (fix applied + verified)
- To assign an owner to a debt
- To query the current state of the registry

## Method (MANDATORY)

### Step 1: Receive a debt management operation
Operations:
- `register` : add a new debt to the registry (with reason)
- `update_status` : change status (open → in_progress → resolved)
- `assign_owner` : set an owner (user/team)
- `set_due_date` : schedule a re-evaluation
- `query` : list debts with filters (status, owner, severity, due_date)
- `archive` : move to cold storage after 1 year resolved

### Step 2: Validate
- Every operation MUST have a reason (audit trail)
- `register` MUST have `accepted_reason` if status is "accepted"
- `update_status` to "resolved" MUST be paired with a fix_id (verified)

### Step 3: Persist to KG (V2)
All operations are persisted to the KG as:
- Updates to `Debt` node metadata
- New edges (e.g. `assigned_to` if owner is a Component/ADR)
- Decision nodes for "accepted" status (with `accepted_reason`)

### Step 4: Sync to Vault (V2)
After every operation, sync the relevant slice of the KG to the vault (per ADR-0023).

### Step 5: Critic Engine
Critic validates:
- `accepted_reason` must be non-trivial (≥ 50 chars, not "TODO" or "later")
- `due_date` must be in the future
- `owner` must exist in the system (else flagged as orphan)

## What I produce
- Updated KG nodes (Debt + edges)
- Updated `debt-registry.json` (V1 compat)
- Updated vault slice (KG → Obsidian)
- `debt-manage.log` : audit trail

## Tools used
- `tools/registry.py` : CRUD operations
- `kg_store.py` (Layer 0) : persistence
- `kg_sync.py` (Layer 0) : vault projection
- `skills/critic/SKILL.md` : validation

## Non-NEGOTIABLE rules

1. **Every debt has a status** : open | in_progress | accepted | resolved
2. **Every accepted debt has a reason** : why we're not fixing it now
3. **Every debt has a due_date or open-ended review** : when to re-evaluate
4. **No orphan owners** : owner must reference a valid identity
5. **Critic validation** : every operation is reviewed
6. **Audit trail** : every operation is logged with timestamp + reason
