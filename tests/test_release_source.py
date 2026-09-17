"""One source resolver: selector conflicts refuse, and every command agrees.

ADR-0019 sections 1–3: `resolve_release_source()` is the only decision, and it
validates before precedence — contradictory selectors are refused, never
ordered. The machine configuration is machine scope (a repository cannot
redirect a user's updates), reserved names cannot be redefined, and a named
provider is anonymous in V1.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.lifecycle_support import LifecycleTestCase, write_text
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import release_source as sourcelib
from ainative.lifecycle.errors import LifecycleError


class TempHome(unittest.TestCase):

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ainative-source-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.root / "home"
        self.home.mkdir()
        self.mirror = self.root / "mirror"
        self.mirror.mkdir()

    def write_config(self, payload: dict) -> Path:
        return write_text(sourcelib.config_path(self.home), json.dumps(payload) + "\n")


class SelectorMatrix(TempHome):

    def resolve(self, **environment):
        return sourcelib.resolve_release_source(environ=environment, home=self.home)

    def test_nothing_selected_is_the_builtin_github(self):
        source = self.resolve()
        self.assertEqual(source.kind, sourcelib.KIND_GITHUB)
        self.assertTrue(source.authenticated)
        self.assertEqual(source.endpoint.auth_origin, "https://api.github.com")
        self.assertEqual(source.metadata_url, providerlib.DEFAULT_RELEASE_URL)

    def test_the_local_pair_resolves_to_the_mirror(self):
        source = self.resolve(AINATIVE_UPDATE_PROVIDER="local",
                              AINATIVE_UPDATE_LOCAL_DIR=str(self.mirror))
        self.assertEqual(source.kind, sourcelib.KIND_LOCAL)
        self.assertEqual(source.directory, self.mirror)
        self.assertFalse(source.authenticated)

    def test_a_local_dir_without_the_explicit_provider_is_a_conflict(self):
        with self.assertRaises(LifecycleError) as raised:
            self.resolve(AINATIVE_UPDATE_LOCAL_DIR=str(self.mirror))
        self.assertEqual(raised.exception.code, "UPDATE_SOURCE_CONFLICT")

    def test_the_url_mixed_with_a_selector_is_a_conflict(self):
        cases = ({"AINATIVE_UPDATE_PROVIDER": "github"},
                 {"AINATIVE_UPDATE_LOCAL_DIR": str(self.mirror)},
                 {"AINATIVE_UPDATE_PROVIDER": "local",
                  "AINATIVE_UPDATE_LOCAL_DIR": str(self.mirror)})
        for extra in cases:
            with self.subTest(extra=extra):
                with self.assertRaises(LifecycleError) as raised:
                    self.resolve(AINATIVE_UPDATE_URL="https://mirror.example/releases/latest",
                                 **extra)
                self.assertEqual(raised.exception.code, "UPDATE_SOURCE_CONFLICT")

    def test_the_url_alone_is_anonymous(self):
        source = self.resolve(AINATIVE_UPDATE_URL="https://mirror.example/releases/latest")
        self.assertEqual(source.kind, sourcelib.KIND_ANONYMOUS)
        self.assertFalse(source.authenticated)
        self.assertIsNone(source.endpoint.auth_origin)

    def test_the_builtin_name_and_its_alias_resolve_to_github(self):
        for name in ("github", "release-api"):
            self.assertEqual(self.resolve(AINATIVE_UPDATE_PROVIDER=name).kind,
                             sourcelib.KIND_GITHUB)

    def test_an_unknown_provider_name_is_refused(self):
        with self.assertRaises(LifecycleError) as raised:
            self.resolve(AINATIVE_UPDATE_PROVIDER="carrier-pigeon")
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")

    def test_local_without_a_directory_is_refused(self):
        with self.assertRaises(LifecycleError) as raised:
            self.resolve(AINATIVE_UPDATE_PROVIDER="local")
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")


class MachineConfig(TempHome):

    def test_a_named_provider_resolves_anonymously(self):
        self.write_config({"schema_version": 1, "providers": {
            "internal": {"api_base_url": "https://releases.internal.example/api"}}})
        source = sourcelib.resolve_release_source(
            environ={"AINATIVE_UPDATE_PROVIDER": "internal"}, home=self.home)
        self.assertEqual(source.kind, sourcelib.KIND_NAMED)
        self.assertFalse(source.authenticated)
        self.assertEqual(source.metadata_url,
                         "https://releases.internal.example/api/releases/latest")

    def test_the_default_provider_applies_when_nothing_is_selected(self):
        self.write_config({"schema_version": 1, "default_provider": "internal",
                           "providers": {"internal": {
                               "api_base_url": "https://releases.internal.example/api"}}})
        source = sourcelib.resolve_release_source(environ={}, home=self.home)
        self.assertEqual(source.provider_name, "internal")

    def test_the_default_local_requires_a_directory(self):
        self.write_config({"schema_version": 1, "default_provider": "local"})
        with self.assertRaises(LifecycleError) as raised:
            sourcelib.resolve_release_source(environ={}, home=self.home)
        self.assertEqual(raised.exception.code, "RELEASE_CONFIG_INVALID")

    def test_a_reserved_name_cannot_be_redefined(self):
        self.write_config({"schema_version": 1, "providers": {
            "github": {"api_base_url": "https://evil.example/api"}}})
        with self.assertRaises(LifecycleError) as raised:
            sourcelib.resolve_release_source(environ={}, home=self.home)
        self.assertEqual(raised.exception.code, "RELEASE_CONFIG_INVALID")

    def test_the_release_api_alias_cannot_be_redefined(self):
        """A config must never declare a provider a built-in alias shadows (#178)."""

        self.write_config({"schema_version": 1, "providers": {
            "release-api": {"api_base_url": "https://evil.example/api"}}})
        with self.assertRaises(LifecycleError) as raised:
            sourcelib.resolve_release_source(environ={}, home=self.home)
        self.assertEqual(raised.exception.code, "RELEASE_CONFIG_INVALID")

    def test_the_gitlab_provider_requires_a_project_reference(self):
        with self.assertRaises(LifecycleError) as raised:
            sourcelib.resolve_release_source(
                environ={"AINATIVE_UPDATE_PROVIDER": "gitlab"}, home=self.home)
        self.assertEqual(raised.exception.code, "RELEASE_CONFIG_INVALID")

    def test_the_gitlab_provider_resolves_with_its_configured_project(self):
        self.write_config({"schema_version": 1, "providers": {
            "gitlab": {"release_project_ref": "group/sub/project"}}})
        source = sourcelib.resolve_release_source(
            environ={"AINATIVE_UPDATE_PROVIDER": "gitlab"}, home=self.home)
        self.assertEqual(source.kind, sourcelib.KIND_GITLAB)
        self.assertEqual(source.project_ref, "group/sub/project")
        self.assertTrue(source.authenticated)
        self.assertEqual(source.endpoint.auth_header, "PRIVATE-TOKEN")
        self.assertEqual(source.endpoint.auth_origin, "https://gitlab.com")
        self.assertEqual(source.endpoint.api_base_url, "https://gitlab.com/api/v4")

    def test_a_gitlab_project_reference_is_not_a_url(self):
        self.write_config({"schema_version": 1, "providers": {
            "gitlab": {"release_project_ref": "https://gitlab.com/group/project"}}})
        with self.assertRaises(LifecycleError) as raised:
            sourcelib.resolve_release_source(
                environ={"AINATIVE_UPDATE_PROVIDER": "gitlab"}, home=self.home)
        self.assertEqual(raised.exception.code, "RELEASE_CONFIG_INVALID")

    def test_a_custom_auth_origin_is_refused_in_v1(self):
        self.write_config({"schema_version": 1, "providers": {
            "internal": {"api_base_url": "https://x.example/api",
                         "auth_origin": "https://x.example"}}})
        with self.assertRaises(LifecycleError) as raised:
            sourcelib.resolve_release_source(
                environ={"AINATIVE_UPDATE_PROVIDER": "internal"}, home=self.home)
        self.assertEqual(raised.exception.code, "RELEASE_CONFIG_INVALID")

    def test_a_future_config_schema_is_refused_not_guessed(self):
        self.write_config({"schema_version": 2, "providers": {}})
        with self.assertRaises(LifecycleError) as raised:
            sourcelib.resolve_release_source(environ={}, home=self.home)
        self.assertEqual(raised.exception.code, "RELEASE_CONFIG_INVALID")

    def test_describe_turns_a_conflict_into_a_state(self):
        record = sourcelib.describe(environ={"AINATIVE_UPDATE_LOCAL_DIR": "x"},
                                    home=self.home)
        self.assertEqual(record["kind"], "refused")
        self.assertEqual(record["state"], "UPDATE_SOURCE_CONFLICT")
        self.assertIn("Release source", sourcelib.describe_lines(record)[0])


class ProviderBuild(TempHome):

    def test_build_delegates_to_the_resolver(self):
        with mock.patch.object(sourcelib, "load_machine_config", lambda home=None: {}), \
                mock.patch.dict(os.environ, {
                    "AINATIVE_UPDATE_PROVIDER": "local",
                    "AINATIVE_UPDATE_LOCAL_DIR": str(self.mirror)}, clear=False):
            built = providerlib.build("stable")
        self.assertIsInstance(built, providerlib.LocalDirectoryProvider)
        self.assertEqual(built.root, self.mirror)

    def test_build_of_the_default_is_the_github_endpoint_provider(self):
        for name in (providerlib.PROVIDER_ENV, providerlib.LOCAL_SOURCE_ENV,
                     providerlib.RELEASE_URL_ENV):
            os.environ.pop(name, None)
        with mock.patch.object(sourcelib, "load_machine_config", lambda home=None: {}):
            built = providerlib.build("stable")
        self.assertIsInstance(built, providerlib.ReleaseApiProvider)
        self.assertEqual(built.endpoint.auth_origin, "https://api.github.com")
        self.assertEqual(built.url, providerlib.DEFAULT_RELEASE_URL)

    def test_build_of_an_anonymous_url_wears_no_credential(self):
        with mock.patch.object(sourcelib, "load_machine_config", lambda home=None: {}), \
                mock.patch.dict(os.environ, {
                    "AINATIVE_UPDATE_URL": "https://mirror.example/releases/latest"}):
            built = providerlib.build("stable")
        self.assertIsNone(built.endpoint.auth_origin)
        self.assertEqual(built._token(), "")


class Diagnostics(LifecycleTestCase):

    def test_status_and_doctor_display_the_source_without_secrets(self):
        self.install("standard")
        report = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(report["release_source"]["kind"], "github")
        self.assertTrue(report["release_source"]["authenticated"])
        text = self.cli("status").stdout
        self.assertIn("Release source", text)
        self.assertIn("authenticated: yes", text)
        doctor = json.loads(self.cli("doctor", "--json").stdout)
        self.assertEqual(doctor["release_source"]["reason"],
                         report["release_source"]["reason"])

    def test_a_selector_conflict_is_identical_across_commands(self):
        """Scenario P: one resolver, one refusal, everywhere."""

        self.install("standard")
        environment = {"AINATIVE_UPDATE_LOCAL_DIR": str(self.root / "mirror")}
        with mock.patch.dict(os.environ, environment):
            check = self.cli("update", "check", "--strict", "--json")
            self.assertEqual(check.returncode, 1)
            checked = json.loads(check.stdout)
            self.assertEqual(checked["status"], "CHECK_FAILED")
            self.assertIn("never ordered", checked["detail"])
            update = self.cli("update", "--json")
            self.assertEqual(update.returncode, 2)
            self.assertEqual(json.loads(update.stdout)["error"], "UPDATE_SOURCE_CONFLICT")
            status = json.loads(self.cli("status", "--json").stdout)
            self.assertEqual(status["release_source"]["state"], "UPDATE_SOURCE_CONFLICT")
            doctor = json.loads(self.cli("doctor", "--json").stdout)
            self.assertEqual(doctor["release_source"]["state"], "UPDATE_SOURCE_CONFLICT")


if __name__ == "__main__":
    unittest.main()
