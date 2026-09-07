"""Unified bounded ContextPlanner core (B2 S1-S9). No providers, no I/O.

Exactly one owner of context selection: every context-producing
surface must become an adapter over `plan()` (PR7 wires the legacy
assembler). Sources are INJECTED as plain records — the planner never
reads files, providers, or the network — so ordering, tiers, budgets
and drift behavior are pure, deterministic, and testable.

Pipeline (B2 S2, provider stages deferred to PR8/PR9):

```text
applicable sources -> scope validation -> freshness record
-> relevance ranking -> typed authority -> conflict/drift
-> tier assignment -> budget enforcement -> bundle
```

Authority and relevance stay separate: tier, then scope precedence,
then authority domain, then input sequence. Task intent may reorder
inside one (tier, authority, scope) group only — it can never remove
a normative source, hide drift, or downgrade authority (B2 S5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import KnowledgeError

ENGINEERING_POLICY = "ENGINEERING_POLICY"
ARCHITECTURE_DECISION = "ARCHITECTURE_DECISION"
IMPLEMENTATION_FACT = "IMPLEMENTATION_FACT"
MODULE_CONSTRAINT = "MODULE_CONSTRAINT"
BEHAVIOURAL_EVIDENCE = "BEHAVIOURAL_EVIDENCE"
FAILURE_PREVENTION = "FAILURE_PREVENTION"
INFORMATIVE_RESEARCH = "INFORMATIVE_RESEARCH"
HISTORICAL_OBSERVATION = "HISTORICAL_OBSERVATION"
UNTRUSTED = "UNTRUSTED"
DERIVED = "DERIVED"

DOMAINS = frozenset({ENGINEERING_POLICY, ARCHITECTURE_DECISION,
                     IMPLEMENTATION_FACT, MODULE_CONSTRAINT,
                     BEHAVIOURAL_EVIDENCE, FAILURE_PREVENTION,
                     INFORMATIVE_RESEARCH, HISTORICAL_OBSERVATION,
                     UNTRUSTED, DERIVED})

KIND_DOMAIN = {
    "agents": ENGINEERING_POLICY,
    "policy": ENGINEERING_POLICY,
    "adr": ARCHITECTURE_DECISION,
    "source": IMPLEMENTATION_FACT,
    "code": IMPLEMENTATION_FACT,
    "ai-context": MODULE_CONSTRAINT,
    "test": BEHAVIOURAL_EVIDENCE,
    "kfp": FAILURE_PREVENTION,
    "failure-pattern": FAILURE_PREVENTION,
    "research": INFORMATIVE_RESEARCH,
    "session": HISTORICAL_OBSERVATION,
    "note": HISTORICAL_OBSERVATION,
    "candidate": UNTRUSTED,
    "summary": DERIVED,
    "continuity": HISTORICAL_OBSERVATION,
}

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"
TIER_D = "D"

TIER_OF_DOMAIN = {
    ENGINEERING_POLICY: TIER_A,
    MODULE_CONSTRAINT: TIER_A,
    FAILURE_PREVENTION: TIER_A,
    ARCHITECTURE_DECISION: TIER_A,
    IMPLEMENTATION_FACT: TIER_D,
    BEHAVIOURAL_EVIDENCE: TIER_D,
    INFORMATIVE_RESEARCH: TIER_D,
    HISTORICAL_OBSERVATION: TIER_D,
    UNTRUSTED: TIER_D,
    DERIVED: TIER_D,
}

AUTHORITY_ORDER = (ENGINEERING_POLICY, ARCHITECTURE_DECISION,
                   MODULE_CONSTRAINT, FAILURE_PREVENTION,
                   IMPLEMENTATION_FACT, BEHAVIOURAL_EVIDENCE,
                   INFORMATIVE_RESEARCH, HISTORICAL_OBSERVATION,
                   UNTRUSTED, DERIVED)

SCOPE_ORDER = ("module", "project", "repository", "global")

FRESHNESS = frozenset({"FRESH", "STALE", "UNKNOWN"})

KNOWLEDGE_TYPES = frozenset({"PRESCRIPTIVE", "PROHIBITIVE", "CONDITIONAL",
                             "DESCRIPTIVE", "HISTORICAL"})


@dataclass(frozen=True)
class Budgets:
    max_bytes: int = 65536
    max_items: int = 64


@dataclass
class PlannedItem:
    source: str
    scope: str
    authority_domain: str
    tier: str
    freshness: str
    excerpt: str
    byte_cost: int
    drift: bool = False
    reason_included: str = ""

    def to_record(self) -> dict[str, Any]:
        return {"source": self.source, "scope": self.scope,
                "authority_domain": self.authority_domain, "tier": self.tier,
                "freshness": self.freshness, "excerpt": self.excerpt,
                "byte_cost": self.byte_cost, "drift": self.drift,
                "reason_included": self.reason_included}


@dataclass
class ContextBundle:
    items: list[PlannedItem] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    total_bytes: int = 0
    tokens_per_tier: dict[str, int] = field(default_factory=dict)
    recall: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {"items": [item.to_record() for item in self.items],
                "dropped": self.dropped, "total_bytes": self.total_bytes,
                "tokens_per_tier": self.tokens_per_tier,
                "recall": self.recall}


def _scope_root(scope: str) -> str:
    return scope.split("/", 1)[0] if "/" in scope else scope


def _scope_applies(source_scope: str, focus: list[str],
                   shared_roots: frozenset[str]) -> bool:
    """Applicability: exact, ancestor, or configured-shared. Pure function."""

    root = _scope_root(source_scope)
    if root not in ("module", "project", "repository", "global"):
        return False
    if root == "global":
        return source_scope != "global" and source_scope in {
            f"global/{name}" for name in shared_roots}
    if not focus:
        return True
    if source_scope in focus:
        return True
    if source_scope in ("repository", "project"):
        return True
    return any(focus_scope == source_scope
               or focus_scope.startswith(source_scope + "/")
               for focus_scope in focus)


def _authority_of(kind: str) -> str:
    return KIND_DOMAIN.get(kind, UNTRUSTED)


def _tier_of(domain: str, knowledge_type: str | None) -> str:
    if knowledge_type == "PROHIBITIVE":
        return TIER_A
    if domain in TIER_OF_DOMAIN:
        return TIER_OF_DOMAIN[domain]
    return TIER_D


def candidate_source(record: dict) -> dict[str, Any]:
    """Adapt a B1 candidate record to a planner source (UNTRUSTED). Pure."""

    scope = record.get("scope", {})
    project = scope.get("project") if isinstance(scope, dict) else None
    return {"kind": "candidate",
            "locator": str(record.get("candidate_id", "candidate")),
            "scope": f"project/{project}" if project else "repository",
            "identity_key": record.get("identity", {}).get("identity_key")
            if isinstance(record.get("identity"), dict) else None,
            "assertion_hash": record.get("assertion_hash"),
            "excerpt": str(record.get("claim", ""))}


def continuity_source(entry: dict) -> dict[str, Any]:
    """Adapt a working-continuity entry to a Tier B source. Pure."""

    return {"kind": "continuity",
            "locator": str(entry.get("locator", "continuity")),
            "scope": str(entry.get("scope", "project")),
            "excerpt": str(entry.get("text", "")),
            "tier": TIER_B}


def _collect(sources: list[dict], focus_scopes: list[str],
             roots: frozenset[str], allow_shared: bool) -> tuple[list, list]:
    """Scope, authority and tier per source; rejects carry reasons."""

    staged, dropped = [], []
    for sequence, raw in enumerate(sources):
        if not isinstance(raw, dict):
            dropped.append({"locator": "?", "reason": "not a source object"})
            continue
        locator = str(raw.get("locator", f"source-{sequence}"))
        scope = str(raw.get("scope", ""))
        if not _scope_applies(scope, focus_scopes, roots):
            dropped.append({"locator": locator, "reason": "scope inapplicable"})
            continue
        if _scope_root(scope) == "global" and not allow_shared:
            dropped.append({"locator": locator, "reason": "shared scope denied"})
            continue
        domain = _authority_of(str(raw.get("kind", "")))
        claimed = raw.get("authority_domain")
        if claimed is not None:
            if claimed not in DOMAINS:
                dropped.append({"locator": locator,
                                "reason": "invalid authority domain"})
                continue
            domain = claimed
        tier = str(raw.get("tier") or _tier_of(domain, raw.get("knowledge_type")))
        if tier not in (TIER_A, TIER_B, TIER_C, TIER_D):
            dropped.append({"locator": locator, "reason": "unknown tier"})
            continue
        freshness = str(raw.get("freshness", "UNKNOWN"))
        if freshness not in FRESHNESS:
            freshness = "UNKNOWN"
        staged.append({"locator": locator, "scope": scope, "domain": domain,
                       "tier": tier, "freshness": freshness,
                       "excerpt": str(raw.get("excerpt", "")),
                       "identity_key": raw.get("identity_key"),
                       "assertion_hash": raw.get("assertion_hash"),
                       "drift": False})
    return staged, dropped


def _flag_drift(staged: list) -> None:
    """Mark same-identity disagreements; stale sides never trigger."""

    by_identity: dict[str, list[dict]] = {}
    for item in staged:
        if item["identity_key"]:
            by_identity.setdefault(str(item["identity_key"]), []).append(item)
    for members in by_identity.values():
        hashes = {str(member["assertion_hash"]) for member in members}
        if len(hashes) > 1 and all(member["freshness"] != "STALE"
                                   for member in members):
            for member in members:
                member["drift"] = True


def _rank_key(emphasis: str | None):
    """Total order: tier, scope, authority, emphasis, content. No input order."""

    def _rank(item: dict) -> tuple:
        scope_rank = SCOPE_ORDER.index(_scope_root(item["scope"])) \
            if _scope_root(item["scope"]) in SCOPE_ORDER else len(SCOPE_ORDER)
        authority_rank = AUTHORITY_ORDER.index(item["domain"]) \
            if item["domain"] in AUTHORITY_ORDER else len(AUTHORITY_ORDER)
        focus_hit = 0
        if emphasis and emphasis in item["excerpt"].lower():
            focus_hit = -1
        return (item["tier"], scope_rank, authority_rank, focus_hit,
                item["locator"], item["excerpt"])

    return _rank


def _enforce(staged: list, dropped: list, limits: Budgets,
             emphasis: str | None) -> ContextBundle:
    """Rank, overflow-check Tier A, then bound. Pure function."""

    staged.sort(key=_rank_key(emphasis))
    tier_a_bytes = sum(len(item["excerpt"].encode("utf-8"))
                       for item in staged if item["tier"] == TIER_A)
    if tier_a_bytes > limits.max_bytes:
        from .errors import KnowledgeError
        raise KnowledgeError("KNOWLEDGE_MANDATORY_CONTEXT_OVERFLOW",
                             f"Tier A needs {tier_a_bytes} bytes "
                             f"(budget {limits.max_bytes}); reduce policy bloat, "
                             "split playbooks, or use a larger harness")
    bundle = ContextBundle(recall={"requested": False,
                                   "reason": "no recall providers in core"})
    used = 0
    for item in staged:
        cost = len(item["excerpt"].encode("utf-8"))
        if len(bundle.items) >= limits.max_items or used + cost > limits.max_bytes:
            dropped.append({"locator": item["locator"],
                            "reason": "budget exceeded"})
            continue
        used += cost
        bundle.items.append(PlannedItem(
            source=item["locator"], scope=item["scope"],
            authority_domain=item["domain"], tier=item["tier"],
            freshness=item["freshness"], excerpt=item["excerpt"],
            byte_cost=cost, drift=item["drift"],
            reason_included="applicable " + item["tier"]))
    bundle.total_bytes = used
    for item in bundle.items:
        bundle.tokens_per_tier[item.tier] = \
            bundle.tokens_per_tier.get(item.tier, 0) + item.byte_cost // 4
    bundle.dropped = dropped
    return bundle


def plan(sources: list[dict], *, focus: list[str] | None = None,
         intent: dict | None = None,
         budgets: Budgets | None = None,
         shared_roots: frozenset[str] | set[str] = frozenset(),
         allow_shared: bool = False) -> ContextBundle:
    """Select, order and bound context. Pure function, no I/O."""

    limits = budgets or Budgets()
    roots = frozenset(shared_roots) if allow_shared else frozenset()
    emphasis = str((intent or {}).get("emphasis", "")).lower() or None
    staged, dropped = _collect(sources, list(focus or []), roots, allow_shared)
    _flag_drift(staged)
    return _enforce(staged, dropped, limits, emphasis)

__all__ = ["ENGINEERING_POLICY", "ARCHITECTURE_DECISION",
           "IMPLEMENTATION_FACT", "MODULE_CONSTRAINT",
           "BEHAVIOURAL_EVIDENCE", "FAILURE_PREVENTION",
           "INFORMATIVE_RESEARCH", "HISTORICAL_OBSERVATION",
           "UNTRUSTED", "DERIVED", "DOMAINS", "TIER_A", "TIER_B",
           "TIER_C", "TIER_D", "Budgets", "PlannedItem", "ContextBundle",
           "candidate_source", "continuity_source", "plan"]
