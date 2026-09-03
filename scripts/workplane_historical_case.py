"""Record one blind historical validation case without breaking its blindness.

The gate this serves cannot be closed by a script, because it needs a defect
that the person or agent authoring the Work Contract has not seen. What a
script can do is make the blindness checkable afterwards, so a case is either
properly conducted or visibly not:

    seal    an organiser fixes the defect and the evaluator-visible bundle,
            storing only their digests
    record  the evaluator's contract and the frozen verdict, once
    reveal  the defect, refused unless a verdict is already frozen and the
            defect matches what was sealed

A case file that reaches `reveal` therefore proves the verdict existed before
the defect was disclosed. See
docs/verified-work-plane-v2-historical-validation-protocol.md.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative_workplane.contracts import canonical_digest

CLASSIFICATIONS = ("DETECTED", "INDIRECTLY_EXPOSED", "MISSED", "NOT_REPRESENTABLE_FROM_ORIGINAL_REQUIREMENTS")


class CaseError(RuntimeError):
    """A case operation that would break the protocol."""


def _digest_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def bundle_digest(directory: Path) -> str:
    """Digest every file an evaluator may see, deterministically."""

    files = {str(path.relative_to(directory)).replace("\\", "/"): _digest_file(path) for path in sorted(directory.rglob("*")) if path.is_file()}
    if not files:
        raise CaseError("EMPTY_BUNDLE")
    return canonical_digest(files)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CaseError("UNREADABLE_CASE") from error


def _write(path: Path, case: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def seal(*, issue: str, pre_fix_commit: str, defect: Path, bundle: Path, output: Path) -> dict:
    """Fix what the evaluator may see and what they must not, by digest only."""

    case = {
        "schema_version": 1,
        "issue": issue,
        "pre_fix_commit": pre_fix_commit,
        "input_bundle_digest": bundle_digest(bundle),
        "defect_digest": _digest_file(defect),
        "sealed_at": _now(),
        "contract_digest": None,
        "verdict": None,
        "verdict_digest": None,
        "recorded_at": None,
        "revealed_at": None,
        "classification": None,
    }
    _write(output, case)
    return case


def record(*, case_path: Path, contract: Path, verdict: Path) -> dict:
    """Freeze the evaluator's contract and verdict. Once."""

    case = _load(case_path)
    if case.get("verdict") is not None:
        raise CaseError("VERDICT_ALREADY_FROZEN")
    if case.get("revealed_at") is not None:
        raise CaseError("ALREADY_REVEALED")
    decision = json.loads(verdict.read_text(encoding="utf-8"))
    case["contract_digest"] = _digest_file(contract)
    case["verdict"] = decision.get("verdict")
    case["verdict_digest"] = _digest_file(verdict)
    case["recorded_at"] = _now()
    _write(case_path, case)
    return case


def reveal(*, case_path: Path, defect: Path, classification: str) -> dict:
    """Disclose the defect, only against a verdict that is already frozen."""

    case = _load(case_path)
    if case.get("verdict") is None:
        raise CaseError("NO_FROZEN_VERDICT")
    if case.get("revealed_at") is not None:
        raise CaseError("ALREADY_REVEALED")
    if classification not in CLASSIFICATIONS:
        raise CaseError("UNKNOWN_CLASSIFICATION")
    if _digest_file(defect) != case["defect_digest"]:
        raise CaseError("DEFECT_DOES_NOT_MATCH_SEAL")
    case["revealed_at"] = _now()
    case["classification"] = classification
    _write(case_path, case)
    return case


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="step", required=True)

    sealed = commands.add_parser("seal")
    sealed.add_argument("--issue", required=True)
    sealed.add_argument("--pre-fix-commit", required=True)
    sealed.add_argument("--defect", type=Path, required=True)
    sealed.add_argument("--bundle", type=Path, required=True)
    sealed.add_argument("--output", type=Path, required=True)

    recorded = commands.add_parser("record")
    recorded.add_argument("--case", type=Path, required=True)
    recorded.add_argument("--contract", type=Path, required=True)
    recorded.add_argument("--verdict", type=Path, required=True)

    revealed = commands.add_parser("reveal")
    revealed.add_argument("--case", type=Path, required=True)
    revealed.add_argument("--defect", type=Path, required=True)
    revealed.add_argument("--classification", required=True, choices=CLASSIFICATIONS)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.step == "seal":
            case = seal(issue=arguments.issue, pre_fix_commit=arguments.pre_fix_commit, defect=arguments.defect, bundle=arguments.bundle, output=arguments.output)
        elif arguments.step == "record":
            case = record(case_path=arguments.case, contract=arguments.contract, verdict=arguments.verdict)
        else:
            case = reveal(case_path=arguments.case, defect=arguments.defect, classification=arguments.classification)
    except CaseError as refusal:
        # A refusal here is the protocol working, not a crash: report it as a
        # named outcome rather than a traceback.
        print(f"refused: {refusal}", file=sys.stderr)
        return 2
    print(json.dumps(case, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
