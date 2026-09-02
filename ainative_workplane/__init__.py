"""Deterministic contracts for the Verified Work Plane V2.

This package deliberately contains data contracts only. Runtime mutation,
command execution, and convergence are implemented in later PRs.
"""

from .contracts import ContractError, canonical_digest, canonical_json_bytes, canonical_path, generate_uid, validate_artifact
from .controller import ControllerError, WorkController
from .traceability import Gap, TraceabilityResult, analyze
from .evidence import EvidenceError, VerificationEvidence
from .trust import TrustVerdict, evaluate_trust
from .freshness import FreshnessResult, evaluate_checkout_freshness, evaluate_freshness
from .runner import RunnerError, VerificationRunner, load_registry
from .convergence import ConvergenceVerdict, append_convergence, converge, stall_fingerprint
from .snapshot import SnapshotError, build_repository_snapshot, snapshot_files, snapshot_reference
from .cli import main as cli_main
from .integrations import ReadOnlyFinding, collect_findings, memory_summary
from .metrics import PilotMetrics

__all__ = [
    "ContractError",
    "ControllerError",
    "WorkController",
    "Gap",
    "TraceabilityResult",
    "analyze",
    "VerificationEvidence",
    "EvidenceError",
    "TrustVerdict",
    "evaluate_trust",
    "FreshnessResult",
    "evaluate_freshness",
    "evaluate_checkout_freshness",
    "RunnerError",
    "VerificationRunner",
    "load_registry",
    "ConvergenceVerdict",
    "converge",
    "append_convergence",
    "stall_fingerprint",
    "SnapshotError",
    "snapshot_files",
    "build_repository_snapshot",
    "snapshot_reference",
    "cli_main",
    "ReadOnlyFinding",
    "collect_findings",
    "memory_summary",
    "PilotMetrics",
    "canonical_digest",
    "canonical_json_bytes",
    "canonical_path",
    "generate_uid",
    "validate_artifact",
]
