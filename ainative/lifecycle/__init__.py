"""Lifecycle: install, switch, uninstall, update, diagnose, repair.

Nothing in this package imports `ainative_workplane`. That is the invariant
ADR-0009 §1 states and `tests/test_lifecycle_boundaries.py` proves: the Standard
profile must be installable without loading a single authority module, and the
Verified Work Plane must never depend on the layer that installs it.
"""

from __future__ import annotations

from .errors import (EXIT_FAILED, EXIT_INVALID_REQUEST, EXIT_OK, EXIT_RECOVERY_REQUIRED,
                     ERROR_EXIT_CODES, LifecycleError)

__all__ = [
    "LifecycleError",
    "ERROR_EXIT_CODES",
    "EXIT_OK",
    "EXIT_FAILED",
    "EXIT_INVALID_REQUEST",
    "EXIT_RECOVERY_REQUIRED",
]
