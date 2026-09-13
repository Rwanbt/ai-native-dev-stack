#!/usr/bin/env python3
"""Compatibility facade: the machine lifecycle now lives in the package.

The record, the reversal rule and the repair pass are owned by
`ainative.lifecycle.machine` / `ainative.lifecycle.machine_health` so the
installed CLI and this checkout script share one implementation. This module
exists only so code written against the old import path keeps working — it
contains no logic of its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative.lifecycle import machine as _machine  # noqa: E402

SCHEMA_VERSION = _machine.SCHEMA_VERSION
MANIFEST_RELATIVE = _machine.MANIFEST_RELATIVE
STOP_DIRECTORY_NAMES = _machine.STOP_DIRECTORY_NAMES
MachineLifecycleError = _machine.MachineLifecycleError
manifest_path = _machine.manifest_path
digest_file = _machine.digest_file
load = _machine.load
save = _machine.save
uninstall = _machine.uninstall

__all__ = ["SCHEMA_VERSION", "MANIFEST_RELATIVE", "STOP_DIRECTORY_NAMES",
           "MachineLifecycleError", "manifest_path", "digest_file", "load",
           "save", "uninstall"]
