import inspect
import unittest

from ainative.multivault import binding as binding_module
from ainative.multivault.binding import (
    ALLOW_ROOT_FRESH,
    DENY_BINDING_MISSING,
    DENY_ROOT_IDENTITY_UNRECORDED,
    DENY_ROOT_MEASUREMENT_INCOMPLETE,
    DENY_ROOT_STALE,
    root_freshness,
)

BINDING = {"vault": "brain-a", "root_identity": "sha256:4f2a"}


class VaultRootFreshnessTests(unittest.TestCase):
    def test_matching_root_identity_is_fresh(self):
        verdict = root_freshness(BINDING, "sha256:4f2a")
        self.assertEqual(ALLOW_ROOT_FRESH, verdict.decision)

    def test_missing_binding_denies(self):
        self.assertEqual(DENY_BINDING_MISSING, root_freshness(None, "sha256:4f2a").decision)

    def test_unrecorded_operator_identity_denies(self):
        self.assertEqual(
            DENY_ROOT_IDENTITY_UNRECORDED,
            root_freshness({"vault": "brain-a"}, "sha256:4f2a").decision,
        )

    def test_absent_measurement_denies(self):
        self.assertEqual(
            DENY_ROOT_MEASUREMENT_INCOMPLETE,
            root_freshness(BINDING, None).decision,
        )
        self.assertEqual(
            DENY_ROOT_MEASUREMENT_INCOMPLETE,
            root_freshness(BINDING, "").decision,
        )

    def test_replaced_or_moved_root_is_stale(self):
        verdict = root_freshness(BINDING, "sha256:0000")
        self.assertEqual(DENY_ROOT_STALE, verdict.decision)
        self.assertEqual("sha256:4f2a", verdict.recorded_root_identity)
        self.assertEqual("sha256:0000", verdict.measured_root_identity)

    def test_identity_comparison_is_exact_not_normalized(self):
        self.assertEqual(DENY_ROOT_STALE, root_freshness(BINDING, "SHA256:4F2A").decision)

    def test_root_freshness_performs_no_io(self):
        source = inspect.getsource(binding_module.root_freshness)
        for marker in ("open(", "Path(", "os.", "subprocess"):
            self.assertNotIn(marker, source)