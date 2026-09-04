"""Structured substance adapters for verification output.

A zero exit code is not evidence. Each registered command declares which
adapter can read its output and how many observations that output must
contain; a command whose adapter finds nothing where something was required
is reported as SUSPICIOUS_VERIFICATION rather than as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping


class SubstanceError(ValueError):
    """A substance contract the runtime cannot honour."""


ADAPTERS = frozenset({"unittest", "pytest", "json", "exit_only"})

_UNITTEST_RAN = re.compile(r"^Ran (?P<count>\d+) tests? in ", re.MULTILINE)
_UNITTEST_SKIPPED = re.compile(r"skipped=(?P<count>\d+)")
_PYTEST_OUTCOME = re.compile(r"(?P<count>\d+) (?P<outcome>passed|failed|error|errors|skipped|xfailed|xpassed)")
_PYTEST_COLLECTED = re.compile(r"collected (?P<count>\d+) items?")


@dataclass(frozen=True)
class Substance:
    """What an adapter could actually observe in one command's output."""

    observations: int | None
    metadata: dict[str, Any]


def validate_contract(contract: Any) -> dict[str, Any]:
    """Validate one command's declared substance contract."""

    if not isinstance(contract, Mapping):
        raise SubstanceError("INVALID_SUBSTANCE_CONTRACT")
    kind = contract.get("type")
    if kind not in ADAPTERS:
        raise SubstanceError("UNKNOWN_SUBSTANCE_ADAPTER")
    minimum = contract.get("minimum_observations", 1)
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
        raise SubstanceError("INVALID_SUBSTANCE_CONTRACT")
    if kind == "exit_only" and minimum != 0:
        raise SubstanceError("INVALID_SUBSTANCE_CONTRACT")
    return {"type": kind, "minimum_observations": minimum}


def _unittest(text: str) -> Substance:
    match = _UNITTEST_RAN.search(text)
    if match is None:
        return Substance(None, {"adapter": "unittest", "parsed": False})
    executed = int(match.group("count"))
    skipped_match = _UNITTEST_SKIPPED.search(text)
    skipped = int(skipped_match.group("count")) if skipped_match else 0
    failed = 0 if "\nOK" in text or text.startswith("OK") else executed - skipped
    return Substance(executed, {"adapter": "unittest", "parsed": True, "tests_collected": executed, "tests_executed": executed, "tests_skipped": skipped, "tests_failed": failed, "tests_passed": executed - skipped - failed})


def _pytest(text: str) -> Substance:
    outcomes: dict[str, int] = {}
    for match in _PYTEST_OUTCOME.finditer(text):
        outcomes[match.group("outcome")] = int(match.group("count"))
    collected_match = _PYTEST_COLLECTED.search(text)
    if not outcomes and collected_match is None:
        return Substance(None, {"adapter": "pytest", "parsed": False})
    passed = outcomes.get("passed", 0)
    failed = outcomes.get("failed", 0) + outcomes.get("error", 0) + outcomes.get("errors", 0)
    skipped = outcomes.get("skipped", 0)
    collected = int(collected_match.group("count")) if collected_match else passed + failed + skipped
    return Substance(passed + failed + skipped, {"adapter": "pytest", "parsed": True, "tests_collected": collected, "tests_executed": passed + failed + skipped, "tests_passed": passed, "tests_failed": failed, "tests_skipped": skipped})


def _structured_json(text: str) -> Substance:
    try:
        payload = json.loads(text)
    except ValueError:
        return Substance(None, {"adapter": "json", "parsed": False})
    if isinstance(payload, list):
        return Substance(len(payload), {"adapter": "json", "parsed": True, "observations": len(payload)})
    if isinstance(payload, Mapping) and isinstance(payload.get("observations"), int) and not isinstance(payload.get("observations"), bool):
        count = int(payload["observations"])
        return Substance(count, {"adapter": "json", "parsed": True, "observations": count})
    return Substance(None, {"adapter": "json", "parsed": False})


_READERS = {"unittest": _unittest, "pytest": _pytest, "json": _structured_json}


def evaluate(contract: Any, *, stdout: str, stderr: str, exit_code: int | None) -> tuple[bool, dict[str, Any]]:
    """Return whether the result is suspicious, with what the adapter observed.

    @contract An undeclared or unreadable substance contract is suspicious,
    never a silent pass.
    """

    if contract is None:
        return True, {"substance": "undeclared"}
    declared = validate_contract(contract)
    kind = declared["type"]
    minimum = declared["minimum_observations"]
    if kind == "exit_only":
        return False, {"adapter": "exit_only", "minimum_observations": 0}
    measured = _READERS[kind](stdout + stderr)
    metadata = dict(measured.metadata)
    metadata["minimum_observations"] = minimum
    if measured.observations is None:
        return True, metadata
    if exit_code == 0 and measured.observations < minimum:
        return True, metadata
    return False, metadata
