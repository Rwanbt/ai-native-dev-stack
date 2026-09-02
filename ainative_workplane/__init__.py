"""Deterministic contracts for the Verified Work Plane V2.

This package deliberately contains data contracts only. Runtime mutation,
command execution, and convergence are implemented in later PRs.
"""

from .contracts import ContractError, canonical_digest, canonical_json_bytes, canonical_path, generate_uid, validate_artifact
from .controller import ControllerError, WorkController

__all__ = [
    "ContractError",
    "ControllerError",
    "WorkController",
    "canonical_digest",
    "canonical_json_bytes",
    "canonical_path",
    "generate_uid",
    "validate_artifact",
]
