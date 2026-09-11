import tempfile
import unittest
from pathlib import Path

from ainative.multivault.admission import (
    HarnessAutoloadAdapter,
    RepositorySurface,
    SurfaceKind,
    admit_repository,
    scan_repository,
)
from ainative.multivault.capability import ControlLevel, Observation, ObservationMode
from ainative.multivault.schema import SecurityClassification


def adapter(**overrides) -> HarnessAutoloadAdapter:
    fields = {
        "harness": "opencode",
        "harness_version": "1.0.0",
        "adapter_version": "1",
        "probe_version": "1",
        "disable_control": ControlLevel.VERIFIED,
        "observation": Observation(ObservationMode.EVENT),
        "evidence_digest": "sha256:evidence",
    }
    fields.update(overrides)
    return HarnessAutoloadAdapter(**fields)


SENSITIVE_CLASSES = (
    SecurityClassification.TEAM,
    SecurityClassification.CONFIDENTIAL,
    SecurityClassification.CRITICAL,
)


class RepositoryAdmissionTests(unittest.TestCase):
    def test_scan_finds_known_surfaces_with_their_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
            (root / ".mcp.json").write_text("{}", encoding="utf-8")
            (root / "mcp.json").write_text("{}", encoding="utf-8")
            nested = root / "project" / "config"
            nested.mkdir(parents=True)
            (nested / "opencode.json").write_text("{}", encoding="utf-8")
            surfaces = scan_repository(root)
            by_path = {surface.path: surface.kind for surface in surfaces}
            self.assertEqual(SurfaceKind.AGENT_CONFIG, by_path["AGENTS.md"])
            self.assertEqual(SurfaceKind.MCP_CONFIG, by_path[".mcp.json"])
            self.assertEqual(SurfaceKind.MCP_CONFIG, by_path["mcp.json"])
            self.assertEqual(SurfaceKind.PLUGIN_CONFIG, by_path["project/config/opencode.json"])

    def test_scan_is_empty_when_no_surface_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual((), scan_repository(Path(directory)))

    def test_unknown_disable_control_denies_sensitive_classifications(self):
        surfaces = (RepositorySurface("opencode.json", SurfaceKind.PLUGIN_CONFIG),)
        for classification in SENSITIVE_CLASSES:
            for control in (ControlLevel.NONE, ControlLevel.PARTIAL):
                result = admit_repository(surfaces, adapter(disable_control=control), classification)
                self.assertEqual("DENY", result.decision)

    def test_sensitive_admission_denies_without_any_adapter(self):
        for classification in SENSITIVE_CLASSES:
            self.assertEqual("DENY", admit_repository((), None, classification).decision)

    def test_sensitive_admission_denies_without_detected_surfaces_too(self):
        result = admit_repository((), adapter(disable_control=ControlLevel.NONE), SecurityClassification.CRITICAL)
        self.assertEqual("DENY", result.decision)

    def test_probe_backed_adapter_allows_sensitive_classifications(self):
        surfaces = (RepositorySurface("opencode.json", SurfaceKind.PLUGIN_CONFIG),)
        for classification in SENSITIVE_CLASSES:
            self.assertEqual("ALLOW", admit_repository(surfaces, adapter(), classification).decision)

    def test_unbounded_observation_denies_sensitive(self):
        observations = (
            Observation(ObservationMode.NONE),
            Observation(ObservationMode.POLL),
            Observation(ObservationMode.POLL, 0),
        )
        for observation in observations:
            result = admit_repository((), adapter(observation=observation), SecurityClassification.CONFIDENTIAL)
            self.assertEqual("DENY", result.decision)

    def test_incomplete_adapter_identity_never_inherits_proof(self):
        cases = (
            adapter(harness_version=""),
            adapter(adapter_version=""),
            adapter(probe_version=""),
            adapter(evidence_digest=""),
        )
        for candidate in cases:
            result = admit_repository((), candidate, SecurityClassification.CONFIDENTIAL)
            self.assertEqual("DENY", result.decision)

    def test_personal_classification_records_surfaces_without_neutralization_proof(self):
        surfaces = (RepositorySurface("AGENTS.md", SurfaceKind.AGENT_CONFIG),)
        result = admit_repository(surfaces, adapter(disable_control=ControlLevel.NONE), SecurityClassification.PERSONAL)
        self.assertEqual("ALLOW", result.decision)
        self.assertIn("1 surface", result.reason)