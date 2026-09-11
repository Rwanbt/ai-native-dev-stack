import inspect
import os
import tempfile
import unittest
from pathlib import Path

from ainative.multivault import exec_wrapper
from ainative.multivault.exec_wrapper import execute_sensitive
from ainative.multivault.runtime_authority import ImmutableAuthoritativeSecurityState, RuntimeAuthority
from ainative.multivault.schema import AllowedContextEnvelope, SecurityEpoch
from ainative.multivault.sensitive_launch import (
    ALLOW_PHASE_B,
    CARRIED_STATE_FIELDS,
    DENY_CARRIED_STATE_DRIFT,
    DENY_CONTAINMENT,
    DENY_PROVIDER_IDENTITY,
)

BASE_ENV = {"PATH": "C:/tools", "ANTHROPIC_MODEL": "claude-haiku-4-5-20251001"}
CREDENTIAL_PROBES = ("ANTHROPIC_API_KEY", "OBSIDIAN_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "NPM_TOKEN", "SMART_CONNECTIONS_KEY")


def make_authority():
    state = ImmutableAuthoritativeSecurityState(
        security_domain_id="company-a",
        security_epoch=SecurityEpoch("company-a", "1", "auth-1"),
        vault_identity="vault",
        checkout_identity="checkout",
        project_security_id="project",
        classification="CONFIDENTIAL",
        allowed_context_envelope=AllowedContextEnvelope(("/srv",), ("/srv",)),
        approved_model_egress_digest="egress",
        memory_policy_digest="m",
        persistence_assurance_digest="p",
        execution_profile="GUARDED",
        runtime_observation_policy_digest="o",
        authority_instance_id="auth-1",
    )
    return RuntimeAuthority(state)


def measure_ok(**overrides):
    data = {field: f"value-{field}" for field in CARRIED_STATE_FIELDS}
    data.update({"provider_ok": "true", "model_ok": "true", "endpoint_ok": "true", "auth_store_ok": "true", "containment_ok": "true"})
    data.update(overrides)
    return data


class SpawnRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {"pid": 4242}


def run_exec(workspace, measure, spawn, **overrides):
    return execute_sensitive(
        workspace=workspace,
        security_domain_id="company-a",
        checkout_identity="checkout",
        authority=make_authority(),
        envelope=AllowedContextEnvelope(("/srv",), ("/srv",)),
        argv=["claude", "-p", "hi"],
        base_env=BASE_ENV,
        measure=measure,
        spawn=spawn,
        **overrides,
    )


class ExecWrapperTests(unittest.TestCase):
    def clean_workspace(self, base):
        ws = Path(base) / "ws"
        ws.mkdir()
        return ws

    def test_ainative_exec_invokes_sensitive_launch_gate(self):
        with tempfile.TemporaryDirectory() as base:
            calls = {"count": 0}

            def measure():
                calls["count"] += 1
                return measure_ok()

            spawn = SpawnRecorder()
            outcome = run_exec(self.clean_workspace(base), measure, spawn)
            self.assertEqual(ALLOW_PHASE_B, outcome.decision)
            self.assertEqual(2, calls["count"])
            self.assertTrue(outcome.spawned)

    def test_ainative_exec_denial_never_spawns_sensitive_child(self):
        with tempfile.TemporaryDirectory() as base:
            spawn = SpawnRecorder()
            outcome = run_exec(self.clean_workspace(base), lambda: measure_ok(provider_ok="false"), spawn)
            self.assertEqual(DENY_PROVIDER_IDENTITY, outcome.decision)
            self.assertFalse(outcome.spawned)
            self.assertEqual([], spawn.calls)

    def test_ainative_exec_positive_env_only(self):
        with tempfile.TemporaryDirectory() as base:
            spawn = SpawnRecorder()
            outcome = run_exec(self.clean_workspace(base), lambda: measure_ok(), spawn)
            self.assertEqual(BASE_ENV, spawn.calls[0]["env"])
            self.assertEqual(BASE_ENV, outcome.env)

    def test_ainative_exec_parent_env_not_inherited(self):
        with tempfile.TemporaryDirectory() as base:
            spawn = SpawnRecorder()
            run_exec(self.clean_workspace(base), lambda: measure_ok(), spawn)
            self.assertEqual(set(BASE_ENV), set(spawn.calls[0]["env"]))
            self.assertNotEqual(dict(os.environ), spawn.calls[0]["env"])

    def test_ainative_exec_handle_forwarded_only_after_allow(self):
        with tempfile.TemporaryDirectory() as base:
            spawn = SpawnRecorder()
            outcome = run_exec(self.clean_workspace(base), lambda: measure_ok(), spawn)
            self.assertIsNotNone(spawn.calls[0]["runtime_context_handle"])
            self.assertIs(outcome.runtime_context_handle, spawn.calls[0]["runtime_context_handle"])
            denied = run_exec(Path(base) / "ws", lambda: measure_ok(provider_ok="false"), SpawnRecorder())
            self.assertIsNone(denied.runtime_context_handle)

    def test_ainative_exec_envelope_forwarded_only_after_allow(self):
        with tempfile.TemporaryDirectory() as base:
            spawn = SpawnRecorder()
            outcome = run_exec(self.clean_workspace(base), lambda: measure_ok(), spawn)
            forwarded = spawn.calls[0]["allowed_context_envelope"]
            self.assertEqual(AllowedContextEnvelope(("/srv",), ("/srv",)), forwarded)
            self.assertIs(outcome.allowed_context_envelope, forwarded)
            denied = run_exec(Path(base) / "ws", lambda: measure_ok(provider_ok="false"), SpawnRecorder())
            self.assertIsNone(denied.allowed_context_envelope)

    def test_ainative_exec_reports_exact_gate_denial_code(self):
        with tempfile.TemporaryDirectory() as base:
            calls = {"count": 0}

            def measure():
                calls["count"] += 1
                return measure_ok(**({"provider_principal": "changed"} if calls["count"] > 1 else {}))

            outcome = run_exec(self.clean_workspace(base), measure, SpawnRecorder())
            self.assertEqual(DENY_CARRIED_STATE_DRIFT, outcome.decision)
            self.assertEqual(DENY_CARRIED_STATE_DRIFT, outcome.denial_code)

    def test_ainative_exec_launcher_is_inside_verified_containment(self):
        with tempfile.TemporaryDirectory() as base:
            spawn = SpawnRecorder()
            outcome = run_exec(self.clean_workspace(base), lambda: measure_ok(containment_ok="false"), spawn)
            self.assertEqual(DENY_CONTAINMENT, outcome.decision)
            self.assertEqual([], spawn.calls)

    def test_ainative_exec_child_receives_no_unapproved_credentials(self):
        with tempfile.TemporaryDirectory() as base:
            spawn = SpawnRecorder()
            run_exec(self.clean_workspace(base), lambda: measure_ok(), spawn)
            child_env = spawn.calls[0]["env"]
            for probe in CREDENTIAL_PROBES:
                self.assertNotIn(probe, child_env)

    def test_ainative_exec_cli_contains_no_duplicate_security_policy(self):
        source = inspect.getsource(exec_wrapper)
        self.assertNotIn("AllowedContextEnvelope(", source)
        self.assertNotIn("issue_phase_b_handle", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("canonical_digest", source)

class ExecEnvironmentTests(unittest.TestCase):
    def test_environment_is_required_os_plus_approved_only(self):
        environment = exec_wrapper.positive_child_environment(
            approved={"ANTHROPIC_MODEL": "claude-haiku-4-5-20251001"},
            required_os={"SystemRoot": "C:/Windows", "windir": "C:/Windows"},
        )
        self.assertEqual(
            {"SystemRoot": "C:/Windows", "windir": "C:/Windows", "ANTHROPIC_MODEL": "claude-haiku-4-5-20251001"},
            environment,
        )

    def test_empty_required_os_values_are_dropped(self):
        environment = exec_wrapper.positive_child_environment(approved={}, required_os={"SystemRoot": "", "COMSPEC": "C:/cmd.exe"})
        self.assertEqual({"COMSPEC": "C:/cmd.exe"}, environment)

    def test_ambient_credentials_and_proxies_absent_unless_approved(self):
        ambient = {
            "SystemRoot": "C:/Windows",
            "OBSIDIAN_API_KEY": "ambient-secret",
            "HTTP_PROXY": "http://proxy.invalid",
            "GIT_ASKPASS": "askpass.exe",
        }
        sanitized_os = {"SystemRoot": ambient["SystemRoot"]}
        environment = exec_wrapper.positive_child_environment(approved={}, required_os=sanitized_os)
        for forbidden in ("OBSIDIAN_API_KEY", "HTTP_PROXY", "GIT_ASKPASS"):
            self.assertNotIn(forbidden, environment)

    def test_explicit_approval_overrides_required_os(self):
        environment = exec_wrapper.positive_child_environment(
            approved={"SystemRoot": "C:/Approved"},
            required_os={"SystemRoot": "C:/Windows"},
        )
        self.assertEqual("C:/Approved", environment["SystemRoot"])
