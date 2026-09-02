"""Verified Work Plane V2 runtime.

Work contracts are written by one controller, verification is observed by a
constrained runner, and convergence is decided deterministically from bound
evidence. Narrative artifacts and language models propose; nothing here lets
them decide.
"""

__version__ = "0.1.0"

from .contracts import SUPPORTED_SCHEMA_VERSIONS, ContractError, canonical_digest, canonical_json_bytes, canonical_path, generate_uid, validate_artifact
from .controller import ControllerError, WorkController
from .traceability import Gap, TraceabilityResult, analyze
from .evidence import EvidenceError, VerificationEvidence
from .trust import TRUST_LEVELS, TrustVerdict, evaluate_trust
from .authorization import UNWAIVABLE, apply_authorizations
from .freshness import FreshnessResult, evaluate_checkout_freshness, evaluate_freshness
from .runner import PREVIEW_CHARS, RunnerError, VerificationRunner, load_registry, redact
from .substance import ADAPTERS, Substance, SubstanceError
from .convergence import ConvergenceVerdict, append_convergence, converge, stall_fingerprint
from .snapshot import SnapshotError, build_repository_snapshot, snapshot_files, snapshot_reference
from .cli import main as cli_main
from .integrations import ReadOnlyFinding, collect_findings, memory_summary
from .metrics import PilotMetrics

__all__ = [
    "__version__",
    "SUPPORTED_SCHEMA_VERSIONS",
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
    "TRUST_LEVELS",
    "UNWAIVABLE",
    "apply_authorizations",
    "FreshnessResult",
    "evaluate_freshness",
    "evaluate_checkout_freshness",
    "RunnerError",
    "VerificationRunner",
    "load_registry",
    "redact",
    "PREVIEW_CHARS",
    "ADAPTERS",
    "Substance",
    "SubstanceError",
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
