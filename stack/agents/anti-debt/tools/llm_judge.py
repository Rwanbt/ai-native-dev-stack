#!/usr/bin/env python3
"""llm_judge.py — LLM-as-judge for semantic quality evaluation of findings.

Evaluates the QUALITY of anti-debt agent outputs beyond structural conformance.
Uses a different model family than the generator to avoid self-preference bias.

Scoring: categorical (good/fair/poor) — NOT numeric (LLMs are better at literacy).

Usage:
    python llm_judge.py evaluate <findings.json> [--repo-path /path/to/repo]
    python llm_judge.py report <results.json>
    python llm_judge.py batch <corpus-dir> [--repo-path /path/to/repo]

Environment:
    LLM_JUDGE_API_KEY   — API key for the judge model
    LLM_JUDGE_MODEL     — Model ID (default: gpt-4o-mini for cost efficiency)
    LLM_JUDGE_PROVIDER  — "openai" or "anthropic" (default: openai)

Security note: The judge has NO tool_use. Input-only, score-only.
See docs/security-boundaries.md — Risk 2.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUBRIC = {
    "faithfulness": {
        "question": "Does the finding accurately reflect what the code actually shows? Is the description factually correct based on the evidence provided?",
        "grades": {
            "good": "Description matches the code reality, no fabrication",
            "fair": "Mostly accurate but minor imprecision or overgeneralization",
            "poor": "Description contradicts the evidence or fabricates details",
        },
    },
    "actionability": {
        "question": "Can a developer act on this finding without needing additional context? Is the next step clear?",
        "grades": {
            "good": "Developer knows exactly what to fix and where",
            "fair": "General direction clear but developer needs to investigate",
            "poor": "Vague, generic, or impossible to act on without significant research",
        },
    },
    "severity_accuracy": {
        "question": "Is the assigned severity proportional to the actual risk? Would a senior engineer agree with the classification?",
        "grades": {
            "good": "Severity matches the real-world impact accurately",
            "fair": "Off by one level (e.g., medium marked high) but defensible",
            "poor": "Grossly miscalibrated (e.g., cosmetic issue marked critical)",
        },
    },
    "evidence_quality": {
        "question": "Does the evidence point to verifiable, concrete code or tool output? Could someone independently confirm this finding?",
        "grades": {
            "good": "Evidence is specific, verifiable, and sufficient",
            "fair": "Evidence exists but is incomplete or partially verifiable",
            "poor": "Evidence is vague, self-referential, or unverifiable",
        },
    },
}

JUDGE_SYSTEM_PROMPT = """You are a strict quality evaluator for a technical debt detection system.
You will be given a finding (a detected technical debt item) and optionally the source code it references.

For each criterion, grade the finding as "good", "fair", or "poor".
Respond ONLY with valid JSON matching this schema:
{
  "grades": {
    "faithfulness": "good|fair|poor",
    "actionability": "good|fair|poor",
    "severity_accuracy": "good|fair|poor",
    "evidence_quality": "good|fair|poor"
  },
  "rationale": "One sentence explaining your overall assessment"
}

Be strict. Grade "poor" when in doubt between "fair" and "poor"."""


def build_judge_prompt(finding: dict, source_code: str | None = None) -> str:
    """Build the user prompt for the judge."""
    parts = ["## Finding to evaluate\n```json"]
    parts.append(json.dumps(finding, indent=2, ensure_ascii=False))
    parts.append("```")

    if source_code:
        parts.append("\n## Source code referenced by evidence")
        parts.append(f"```\n{source_code[:4000]}\n```")

    parts.append("\n## Evaluation criteria")
    for name, criterion in RUBRIC.items():
        parts.append(f"- **{name}**: {criterion['question']}")

    parts.append("\nGrade each criterion. Respond with JSON only.")
    return "\n".join(parts)


def call_judge_api(system_prompt: str, user_prompt: str) -> dict | None:
    """Call the LLM judge API. Returns parsed JSON response or None on failure."""
    provider = os.environ.get("LLM_JUDGE_PROVIDER", "openai")
    api_key = os.environ.get("LLM_JUDGE_API_KEY", "")
    model = os.environ.get("LLM_JUDGE_MODEL", "gpt-4o-mini")

    if not api_key:
        return None

    if provider == "openai":
        return _call_openai(api_key, model, system_prompt, user_prompt)
    elif provider == "anthropic":
        return _call_anthropic(api_key, model, system_prompt, user_prompt)
    return None


def _call_openai(api_key: str, model: str, system: str, user: str) -> dict | None:
    """Call OpenAI-compatible API."""
    try:
        import httpx
    except ImportError:
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                }).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception:
            return None

    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return None


def _call_anthropic(api_key: str, model: str, system: str, user: str) -> dict | None:
    """Call Anthropic API."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({
                "model": model,
                "max_tokens": 300,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }).encode(),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            content = data["content"][0]["text"]
            return json.loads(content)
    except Exception:
        return None


def judge_finding(finding: dict, source_code: str | None = None) -> dict:
    """Evaluate a single finding. Returns grades + metadata."""
    user_prompt = build_judge_prompt(finding, source_code)
    result = call_judge_api(JUDGE_SYSTEM_PROMPT, user_prompt)

    if result is None:
        return {
            "finding_id": finding.get("id", "unknown"),
            "status": "skipped",
            "reason": "no API key or API call failed",
        }

    grades = result.get("grades", {})
    valid_grades = {"good", "fair", "poor"}
    for criterion in RUBRIC:
        if grades.get(criterion) not in valid_grades:
            grades[criterion] = "poor"

    return {
        "finding_id": finding.get("id", "unknown"),
        "status": "evaluated",
        "grades": grades,
        "rationale": result.get("rationale", ""),
        "pass": all(g != "poor" for g in grades.values()),
    }


def judge_batch(findings_path: Path, repo_path: Path | None = None) -> dict:
    """Evaluate all findings in a file."""
    with open(findings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    findings = data if isinstance(data, list) else data.get("findings", data.get("fix_order", []))
    results = []

    for finding in findings:
        source_code = None
        if repo_path:
            source_code = _try_read_source(finding, repo_path)
        result = judge_finding(finding, source_code)
        results.append(result)

    return {
        "metadata": {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(findings_path),
            "total_findings": len(findings),
            "total_evaluated": sum(1 for r in results if r["status"] == "evaluated"),
            "total_skipped": sum(1 for r in results if r["status"] == "skipped"),
        },
        "results": results,
        "summary": _compute_summary(results),
    }


def _try_read_source(finding: dict, repo_path: Path) -> str | None:
    """Try to read source code referenced by a finding's evidence."""
    for ev in finding.get("evidence", []):
        if ev.get("type") == "file_location":
            value = ev.get("value", "")
            file_part = value.split(":")[0]
            candidate = repo_path / file_part
            if candidate.exists():
                try:
                    return candidate.read_text(encoding="utf-8", errors="replace")[:4000]
                except Exception:
                    pass
    location = finding.get("location", {})
    if location.get("file"):
        candidate = repo_path / location["file"]
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace")[:4000]
            except Exception:
                pass
    return None


def _compute_summary(results: list[dict]) -> dict:
    """Compute pass rates per criterion."""
    evaluated = [r for r in results if r["status"] == "evaluated"]
    if not evaluated:
        return {"pass_rate": 0.0, "by_criterion": {}}

    total = len(evaluated)
    pass_count = sum(1 for r in evaluated if r["pass"])

    by_criterion: dict[str, dict[str, int]] = {}
    for criterion in RUBRIC:
        counts = {"good": 0, "fair": 0, "poor": 0}
        for r in evaluated:
            grade = r.get("grades", {}).get(criterion, "poor")
            counts[grade] = counts.get(grade, 0) + 1
        by_criterion[criterion] = {
            **counts,
            "pass_rate": round((counts["good"] + counts["fair"]) / total, 3),
        }

    return {
        "pass_rate": round(pass_count / total, 3),
        "total_evaluated": total,
        "by_criterion": by_criterion,
    }


def judge_report(results: dict) -> str:
    """Generate a markdown report from evaluation results."""
    meta = results.get("metadata", {})
    summary = results.get("summary", {})
    by_criterion = summary.get("by_criterion", {})

    lines = [
        "# LLM-as-Judge Evaluation Report",
        "",
        f"**Date**: {meta.get('evaluated_at', 'unknown')}",
        f"**Source**: `{meta.get('source_file', 'unknown')}`",
        f"**Findings evaluated**: {meta.get('total_evaluated', 0)} / {meta.get('total_findings', 0)}",
        f"**Overall pass rate**: {summary.get('pass_rate', 0):.1%}",
        "",
        "## Pass rates by criterion",
        "",
        "| Criterion | Good | Fair | Poor | Pass Rate |",
        "|-----------|------|------|------|-----------|",
    ]

    for name, stats in by_criterion.items():
        lines.append(
            f"| {name} | {stats.get('good', 0)} | {stats.get('fair', 0)} | "
            f"{stats.get('poor', 0)} | {stats.get('pass_rate', 0):.1%} |"
        )

    lines.extend(["", "## Findings graded 'poor'", ""])
    for r in results.get("results", []):
        if r.get("status") != "evaluated":
            continue
        poor_criteria = [c for c, g in r.get("grades", {}).items() if g == "poor"]
        if poor_criteria:
            lines.append(f"- **{r['finding_id']}**: poor on {', '.join(poor_criteria)}")
            if r.get("rationale"):
                lines.append(f"  - {r['rationale']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="LLM-as-judge for anti-debt findings")
    sub = parser.add_subparsers(dest="command", required=True)

    eval_p = sub.add_parser("evaluate", help="Evaluate findings in a JSON file")
    eval_p.add_argument("findings", type=Path)
    eval_p.add_argument("--repo-path", type=Path, default=None)
    eval_p.add_argument("--output", type=Path, default=None)

    report_p = sub.add_parser("report", help="Generate markdown report from results")
    report_p.add_argument("results", type=Path)

    batch_p = sub.add_parser("batch", help="Evaluate all findings in a corpus directory")
    batch_p.add_argument("corpus_dir", type=Path)
    batch_p.add_argument("--repo-path", type=Path, default=None)
    batch_p.add_argument("--output", type=Path, default=None)

    args = parser.parse_args()

    if args.command == "evaluate":
        results = judge_batch(args.findings, args.repo_path)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Results written to {args.output}")
        else:
            print(judge_report(results))

    elif args.command == "report":
        with open(args.results, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(judge_report(results))

    elif args.command == "batch":
        all_results = []
        for findings_file in args.corpus_dir.rglob("*.json"):
            if "EXPECTED" in findings_file.name:
                continue
            results = judge_batch(findings_file, args.repo_path)
            all_results.append(results)
            evaluated = results["metadata"]["total_evaluated"]
            pr = results["summary"].get("pass_rate", 0)
            print(f"  {findings_file.name}: {evaluated} evaluated, pass rate {pr:.1%}")

        if args.output and all_results:
            combined = {
                "metadata": {
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                    "corpus_dir": str(args.corpus_dir),
                    "files_processed": len(all_results),
                },
                "file_results": all_results,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(combined, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
