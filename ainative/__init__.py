"""AI Native Dev Stack — distribution and lifecycle layer.

This package owns installation, profile selection, uninstallation and updates.
It is deliberately independent of `ainative_workplane`: the lifecycle layer may
invoke the Verified Work Plane, the Verified Work Plane never imports this one,
and the Standard profile operates without loading a single authority module.
See ADR-0009.
"""

from __future__ import annotations

__version__ = "2.0.0"

__all__ = ["__version__"]
