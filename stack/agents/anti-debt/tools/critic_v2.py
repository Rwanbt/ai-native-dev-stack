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

def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "triage" and len(sys.argv) >= 3:
        data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
        findings = data if isinstance(data, list) else data.get("findings", [])
        triaged = triage(findings)
        print(json.dumps({
            "tier_counts": {
                "accepted": len(triaged["accepted"]),
                "review": len(triaged["review"]),
                "rejected": len(triaged["rejected"]),
            },
            "top_5_accepted": triaged["accepted"][:5],
            "review_required_count": len(triaged["review"]),
        }, indent=2, ensure_ascii=False))
        return 0
    if cmd == "score" and len(sys.argv) >= 3:
        data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
        findings = data if isinstance(data, list) else data.get("findings", [])
        out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        plan = build_triage(findings)
        text = json.dumps(plan, indent=2, ensure_ascii=False)
        if out_path:
            out_path.write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    if cmd == "override" and len(sys.argv) >= 5:
        findings_path = Path(sys.argv[2])
        finding_id = sys.argv[3]
        action = sys.argv[4]
        reason = sys.argv[5] if len(sys.argv) > 5 else "no reason provided"
        history_path = Path(sys.argv[6]) if len(sys.argv) > 6 else Path(".debt-history.json")
        history = load_history(history_path)
        # Look up the finding's confidence so calibration can bucket this override.
        orig_conf = None
        try:
            data = json.loads(Path(findings_path).read_text(encoding="utf-8-sig"))
            items = data if isinstance(data, list) else data.get("findings", [])
            for it in items:
                if it.get("id") == finding_id:
                    orig_conf = it.get("confidence")
                    break
        except (OSError, json.JSONDecodeError):
            pass
        try:
            entry = record_override(history, finding_id, action, reason, orig_conf)
        except ValueError as e:
            print(json.dumps({"error": str(e)}))
            return 1
        save_history(history_path, history)
        stats = compute_calibration_stats(history)
        print(json.dumps({"recorded": entry, "calibration_stats": stats}, indent=2))
        return 0
    if cmd == "stats" and len(sys.argv) >= 3:
        history_path = Path(sys.argv[2])
        history = load_history(history_path)
        stats = compute_calibration_stats(history)
        print(json.dumps(stats, indent=2))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
