#!/usr/bin/env python3
"""critic_v2.py — Layer 2: Critic Engine V2 (tiers + override + calibration).

Implements ADR-0021 (Critic self-challenge):
- 3 confidence tiers: reject (<0.6), human-review (0.6-0.7), accept (>=0.7)
  The 0.6 reject floor is the non-negotiable policy (AGENT.md, critic SKILL.md).
- Override tracking: every human decision is logged for future calibration
- Kill switch: if human override rate > 30%, switch to conservative mode
- Score formula from scoring-calibration.md

Usage:
    python3 critic_v2.py score <findings.json> [output.json]
    python3 critic_v2.py override <findings.json> <finding_id> <action> [reason]
    python3 critic_v2.py stats <history.json>
    python3 critic_v2.py triage <findings.json>
"""
from __future__ import annotations
import json
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --- Constants (tunable, see scoring-calibration.md) ---
# Confidence below TIER_REJECT is rejected by default — non-negotiable policy
# documented in AGENT.md (Directive 3) and skills/critic/SKILL.md.
TIER_REJECT = 0.6
TIER_REVIEW = 0.7
KILL_SWITCH_OVERRIDE_RATE = 0.30
WEIGHT_IMPACT = 1.0
WEIGHT_URGENCY = 1.0
WEIGHT_CONFIDENCE = 1.0

SEVERITY_TO_IMPACT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}
EFFORT_TO_DAYS = {
    "XS": 0.05,
    "S": 0.25,
    "M": 1.0,
    "L": 3.0,
    "XL": 10.0,
}
RISK_MULTIPLIER = {"low": 1.0, "medium": 1.5, "high": 2.5}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_score(finding: dict) -> float:
    """Compute priority score for a finding.

    score = (impact * urgency * confidence) / max(effort_days * risk_multiplier, 0.1)
    """
    impact = SEVERITY_TO_IMPACT.get(finding.get("severity", "low"), 1)
    urgency = finding.get("urgency", impact)
    confidence = float(finding.get("confidence", 0.0))
    effort = finding.get("estimated_effort", "M")
    effort_days = EFFORT_TO_DAYS.get(effort, 1.0)
    risk = RISK_MULTIPLIER.get(finding.get("risk_of_fix", "medium"), 1.5)
    effective_effort = max(effort_days * risk, 0.1)
    return round((impact * urgency * confidence) / effective_effort, 2)


def tier(finding: dict) -> str:
    """Classify finding into reject / review / accept tier based on confidence."""
    c = float(finding.get("confidence", 0.0))
    if c < TIER_REJECT:
        return "reject"
    if c < TIER_REVIEW:
        return "review"
    return "accept"


def triage(findings: list) -> dict:
    """Apply tier filter to a list of findings.

    Returns {accepted, review, rejected, with_tier_tag}.
    """
    accepted, review, rejected = [], [], []
    for f in findings:
        t = tier(f)
        annotated = {**f, "tier": t, "score": compute_score(f)}
        if t == "accept":
            accepted.append(annotated)
        elif t == "review":
            review.append(annotated)
        else:
            rejected.append(annotated)
    return {
        "accepted": sorted(accepted, key=lambda x: -x["score"]),
        "review": sorted(review, key=lambda x: -x["score"]),
        "rejected": rejected,
    }


def build_triage(findings: list, project: str = "unknown") -> dict:
    """Build a DETERMINISTIC triage (debt-triage.schema.json) from findings.

    This sorts findings into accept/review/reject tiers by score — it is NOT a
    remediation plan. The remediation plan (DebtPlan, debt-plan.schema.json,
    with `actions` and justified `accepted_debt`) is authored by the LLM
    `debt-plan` skill, which CONSUMES this triage. Keeping the two separate
    respects the deterministic-vs-judgment boundary (Directive 5).
    """
    triaged = triage(findings)
    return {
        "triage_id": f"triage-{uuid.uuid4().hex[:12]}",
        "project": project,
        "created_at": _now(),
        "critic_validation": {
            "engine_version": "v2.0.0",
            "thresholds": {"reject_below": TIER_REJECT, "review_below": TIER_REVIEW},
            "tier_counts": {
                "accepted": len(triaged["accepted"]),
                "review": len(triaged["review"]),
                "rejected": len(triaged["rejected"]),
            },
            "scoring_formula": "(impact * urgency * confidence) / (effort_days * risk_multiplier)",
        },
        "fix_order": triaged["accepted"],
        "human_review_required": triaged["review"],
        "rejected": triaged["rejected"],
    }


# --- Override tracking ---

def load_history(path: Path) -> dict:
    """Load debt-history.json. Returns a fresh history if file is missing."""
    if not path.exists():
        return {
            "schema_version": "1.0.0",
            "created_at": _now(),
            "overrides": [],
            "scans": [],
            "resolutions": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_history(path: Path, history: dict) -> None:
    """Persist history atomically (write-temp-then-rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def record_override(history: dict, finding_id: str, action: str, reason: str,
                    original_confidence: float = None) -> dict:
    """Record a human override decision for a finding.

    action: 'accept_override' (force include), 'reject_override' (force exclude),
            'confirm' (human agrees with critic)

    original_confidence is the finding's confidence at decision time. It is
    REQUIRED for empirical calibration (calibration.py buckets overrides by it);
    without it the calibration loop is blind. Callers should always supply it.
    """
    if action not in ("accept_override", "reject_override", "confirm"):
        raise ValueError(f"invalid action: {action}")
    if len(reason) < 10:
        raise ValueError("reason must be at least 10 characters (per ADR-0021)")
    entry = {
        "override_id": f"ovr-{uuid.uuid4().hex[:12]}",
        "finding_id": finding_id,
        "action": action,
        "reason": reason,
        "timestamp": _now(),
    }
    if original_confidence is not None:
        entry["original_confidence"] = original_confidence
    history.setdefault("overrides", []).append(entry)
    return entry


def compute_calibration_stats(history: dict) -> dict:
    """Compute override statistics for calibration.

    Returns {total_overrides, override_rate, kill_switch_triggered, action_breakdown}.
    """
    overrides = history.get("overrides", [])
    resolutions = history.get("resolutions", [])
    n_resolved = len(resolutions)
    if n_resolved == 0:
        override_rate = 0.0
    else:
        n_changed = sum(1 for o in overrides if "override" in o.get("action", ""))
        override_rate = n_changed / n_resolved
    action_counts = Counter(o.get("action", "unknown") for o in overrides)
    return {
        "total_overrides": len(overrides),
        "total_resolutions": n_resolved,
        "override_rate": round(override_rate, 3),
        "kill_switch_triggered": override_rate > KILL_SWITCH_OVERRIDE_RATE,
        "action_breakdown": dict(action_counts),
    }


# --- CLI ---

def _load_findings(path: str) -> list:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return data if isinstance(data, list) else data.get("findings", [])


def _cmd_triage(argv: list) -> int:
    if len(argv) < 3:
        return _usage()
    triaged = triage(_load_findings(argv[2]))
    print(json.dumps({
        "tier_counts": {k: len(triaged[k]) for k in ("accepted", "review", "rejected")},
        "top_5_accepted": triaged["accepted"][:5],
        "review_required_count": len(triaged["review"]),
    }, indent=2, ensure_ascii=False))
    return 0


def _cmd_score(argv: list) -> int:
    if len(argv) < 3:
        return _usage()
    plan = build_triage(_load_findings(argv[2]))
    text = json.dumps(plan, indent=2, ensure_ascii=False)
    out_path = Path(argv[3]) if len(argv) > 3 else None
    if out_path:
        out_path.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def _lookup_confidence(findings_path: str, finding_id: str):
    """Return the confidence of finding_id in findings_path, or None."""
    try:
        for it in _load_findings(findings_path):
            if it.get("id") == finding_id:
                return it.get("confidence")
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _cmd_override(argv: list) -> int:
    if len(argv) < 5:
        return _usage()
    findings_path, finding_id, action = argv[2], argv[3], argv[4]
    reason = argv[5] if len(argv) > 5 else "no reason provided"
    history_path = Path(argv[6]) if len(argv) > 6 else Path(".debt-history.json")
    history = load_history(history_path)
    orig_conf = _lookup_confidence(findings_path, finding_id)
    try:
        entry = record_override(history, finding_id, action, reason, orig_conf)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 1
    save_history(history_path, history)
    print(json.dumps({"recorded": entry,
                      "calibration_stats": compute_calibration_stats(history)}, indent=2))
    return 0


def _cmd_stats(argv: list) -> int:
    if len(argv) < 3:
        return _usage()
    print(json.dumps(compute_calibration_stats(load_history(Path(argv[2]))), indent=2))
    return 0


def _usage() -> int:
    print(__doc__)
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        return _usage()
    handler = {
        "triage": _cmd_triage, "score": _cmd_score,
        "override": _cmd_override, "stats": _cmd_stats,
    }.get(sys.argv[1])
    return handler(sys.argv) if handler else _usage()


if __name__ == "__main__":
    sys.exit(main())
