"""The pure Work Authority resolver, the claim grammar, and the claim journal.

ADR-0018 splits work management in two: the harness observes remote facts, and
the local layer records them deterministically. These tests pin the local half
— resolution priority and refusals, canonical identities, UTC ordering, the
journal-before-POST invariant, the outcomes, and the explicit abandonment
transition. Nothing here touches the network, and nothing may infer an outcome:
an unreadable journal fails closed.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, write_text
from ainative import claims
from ainative import forge as forgelib
from ainative.lifecycle import state as statelib
from ainative.lifecycle.errors import LifecycleError


class RemoteReading(unittest.TestCase):

    def test_https_and_scp_urls_read_the_same(self):
        self.assertEqual(forgelib.provider_hint("https://github.com/o/r.git"), "github")
        self.assertEqual(forgelib.provider_hint("git@github.com:o/r.git"), "github")
        self.assertEqual(forgelib.provider_hint("ssh://git@gitlab.com/g/s/p.git"), "gitlab")
        self.assertEqual(forgelib.project_identity("git@github.com:o/r.git"), "o/r")
        self.assertEqual(forgelib.project_identity("https://gitlab.com/g/s/p.git"), "g/s/p")

    def test_a_self_hosted_host_is_unknown_never_guessed(self):
        self.assertEqual(forgelib.provider_hint("https://git.example.com/o/r.git"), "unknown")
        self.assertIsNone(forgelib.project_identity("https://git.example.com/o/r.git"))

    def test_an_url_without_a_project_is_not_an_identity(self):
        self.assertIsNone(forgelib.project_identity("https://github.com"))
        self.assertIsNone(forgelib.project_identity("https://github.com/only-owner"))


class WorkAuthorityResolution(unittest.TestCase):

    def ref(self, provider: str, project: str) -> forgelib.WorkAuthorityRef:
        return forgelib.WorkAuthorityRef(provider=provider, project=project)

    def test_an_explicit_reference_wins(self):
        resolved = forgelib.resolve_observed_work_authority(
            explicit=self.ref("github", "o/explicit"),
            remotes=forgelib.observe_remotes([("origin", "https://gitlab.com/o/other.git")]))
        self.assertEqual(resolved, self.ref("github", "o/explicit"))

    def test_a_harness_declaration_wins_over_observation(self):
        resolved = forgelib.resolve_observed_work_authority(
            declared=self.ref("gitlab", "g/declared"),
            remotes=forgelib.observe_remotes([("origin", "https://github.com/o/other.git")]))
        self.assertEqual(resolved, self.ref("gitlab", "g/declared"))

    def test_contradicting_statements_refuse_as_mismatch(self):
        with self.assertRaises(LifecycleError) as raised:
            forgelib.resolve_observed_work_authority(
                explicit=self.ref("github", "o/a"), declared=self.ref("gitlab", "g/b"))
        self.assertEqual(raised.exception.code, "WORK_AUTHORITY_MISMATCH")

    def test_one_compatible_candidate_is_an_authority(self):
        resolved = forgelib.resolve_observed_work_authority(
            remotes=forgelib.observe_remotes([("origin", "git@github.com:o/r.git")]))
        self.assertEqual(resolved, self.ref("github", "o/r"))

    def test_two_names_for_the_same_authority_are_not_ambiguous(self):
        resolved = forgelib.resolve_observed_work_authority(
            remotes=forgelib.observe_remotes([
                ("origin", "https://github.com/o/r.git"),
                ("upstream", "git@github.com:o/r")]))
        self.assertEqual(resolved, self.ref("github", "o/r"))

    def test_a_fork_refuses_as_ambiguous_without_preferring_origin(self):
        with self.assertRaises(LifecycleError) as raised:
            forgelib.resolve_observed_work_authority(
                remotes=forgelib.observe_remotes([
                    ("origin", "https://github.com/me/fork.git"),
                    ("upstream", "https://github.com/org/project.git")]))
        self.assertEqual(raised.exception.code, "WORK_AUTHORITY_AMBIGUOUS")
        self.assertEqual(len(raised.exception.detail["candidates"]), 2)

    def test_nothing_usable_refuses_as_unavailable(self):
        with self.assertRaises(LifecycleError) as raised:
            forgelib.resolve_observed_work_authority(remotes=())
        self.assertEqual(raised.exception.code, "WORK_AUTHORITY_UNAVAILABLE")
        with self.assertRaises(LifecycleError) as raised:
            forgelib.resolve_observed_work_authority(
                remotes=forgelib.observe_remotes(
                    [("origin", "https://git.example.com/o/r.git")]))
        self.assertEqual(raised.exception.code, "WORK_AUTHORITY_UNAVAILABLE")


class ClaimGrammar(unittest.TestCase):

    def event(self, identifier: str, created_at: str, actor: str = "github:principal:alice"):
        return claims.ClaimEvent(identifier=identifier, created_at=created_at, actor=actor)

    def test_canonical_identities(self):
        self.assertEqual(claims.principal("github", "alice"),
                         "github:principal:alice")
        self.assertEqual(claims.event_identifier("gitlab", "note", "42"),
                         "gitlab:note:42")
        with self.assertRaises(LifecycleError) as raised:
            claims.event_identifier("gitlab", "telepathy", "42")
        self.assertEqual(raised.exception.code, "CLAIM_INVALID")
        for bad in ("", "two words", "co:lon"):
            with self.assertRaises(LifecycleError):
                claims.principal("github", bad)

    def test_timestamps_normalize_to_utc_and_naive_ones_refuse(self):
        self.assertEqual(claims.to_utc("2026-09-16T12:00:00+02:00"),
                         "2026-09-16T10:00:00+00:00")
        self.assertEqual(claims.to_utc("2026-09-16T10:00:00Z"),
                         "2026-09-16T10:00:00+00:00")
        for bad in ("2026-09-16T10:00:00", "not-a-date"):
            with self.assertRaises(LifecycleError) as raised:
                claims.to_utc(bad)
            self.assertEqual(raised.exception.code, "CLAIM_INVALID")

    def test_winner_is_ordered_by_timestamp_then_identifier(self):
        early = self.event("github:comment:2", "2026-09-16T09:00:00+00:00")
        late = self.event("github:comment:1", "2026-09-16T10:00:00+00:00")
        self.assertEqual(claims.winner([late, early]), early)
        self.assertIsNone(claims.winner([]))

    def test_a_tie_is_broken_by_the_canonical_identifier(self):
        first = self.event("github:comment:1", "2026-09-16T10:00:00+00:00")
        second = self.event("github:comment:2", "2026-09-16T10:00:00+00:00")
        self.assertEqual(claims.winner([second, first]), first)

    def test_duplicate_observations_are_one_event(self):
        event = self.event("github:comment:1", "2026-09-16T10:00:00+00:00")
        self.assertEqual(claims.winner([event, event]), event)

    def test_an_identifier_carrying_two_actors_is_a_conflict(self):
        with self.assertRaises(LifecycleError) as raised:
            claims.winner([
                self.event("github:comment:1", "2026-09-16T10:00:00+00:00",
                           actor="github:principal:alice"),
                self.event("github:comment:1", "2026-09-16T10:00:00+00:00",
                           actor="github:principal:bob")])
        self.assertEqual(raised.exception.code, "CLAIM_CONFLICT")


class ClaimJournal(LifecycleTestCase):

    def authority(self):
        return forgelib.WorkAuthorityRef(provider="github", project="o/r")

    def attempt(self, item: str = "42"):
        return claims.new_attempt(authority=self.authority(), item=item,
                                  principal=claims.principal("github", "alice"))

    def test_begin_writes_pending_before_anything_else(self):
        attempt = self.attempt()
        path = claims.begin(self.project, attempt)
        self.assertTrue(path.is_file())
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["state"], claims.PENDING)
        self.assertIn(attempt.attempt_id, attempt.marker)
        self.assertEqual(record["marker"], attempt.marker)

    def test_an_unwritable_journal_refuses_instead_of_posting(self):
        journal = claims.attempts_root(self.project)
        write_text(journal, "not a directory\n")
        with self.assertRaises(LifecycleError) as raised:
            claims.begin(self.project, self.attempt())
        self.assertEqual(raised.exception.code, "CLAIM_JOURNAL_UNAVAILABLE")

    def test_a_corrupt_entry_fails_closed(self):
        attempt = self.attempt()
        claims.begin(self.project, attempt)
        write_text(claims.attempts_root(self.project) / f"{attempt.attempt_id}.json",
                   "{not json\n")
        with self.assertRaises(LifecycleError) as raised:
            claims.list_attempts(self.project)
        self.assertEqual(raised.exception.code, "CLAIM_JOURNAL_UNAVAILABLE")

    def test_outcomes_are_recorded_and_uncertain_stays_unresolved(self):
        confirmed = self.attempt()
        uncertain = self.attempt(item="43")
        claims.begin(self.project, confirmed)
        claims.begin(self.project, uncertain)
        claims.record_outcome(self.project, confirmed.attempt_id, claims.CONFIRMED)
        claims.record_outcome(self.project, uncertain.attempt_id, claims.UNCERTAIN,
                              note="POST answer was lost")
        states = {attempt.attempt_id: attempt.state
                  for attempt in claims.list_attempts(self.project)}
        self.assertEqual(states[confirmed.attempt_id], claims.CONFIRMED)
        self.assertEqual(states[uncertain.attempt_id], claims.UNCERTAIN)
        self.assertEqual([attempt.attempt_id for attempt in claims.unresolved(self.project)],
                         [uncertain.attempt_id])
        self.assertEqual(claims.load_attempt(self.project, uncertain.attempt_id).note,
                         "POST answer was lost")

    def test_an_unknown_outcome_is_refused(self):
        attempt = self.attempt()
        claims.begin(self.project, attempt)
        with self.assertRaises(LifecycleError) as raised:
            claims.record_outcome(self.project, attempt.attempt_id, "MAYBE")
        self.assertEqual(raised.exception.code, "CLAIM_INVALID")

    def test_abandon_needs_an_explicit_confirmation(self):
        attempt = self.attempt()
        claims.begin(self.project, attempt)
        with self.assertRaises(LifecycleError) as raised:
            claims.abandon(self.project, attempt.attempt_id, confirm=False)
        self.assertEqual(raised.exception.code, "CONFIRMATION_REQUIRED")
        self.assertEqual(claims.load_attempt(self.project, attempt.attempt_id).state,
                         claims.PENDING)

    def test_abandon_is_local_and_the_record_is_retained(self):
        attempt = self.attempt()
        claims.begin(self.project, attempt)
        abandoned = claims.abandon(self.project, attempt.attempt_id, confirm=True)
        self.assertEqual(abandoned.state, claims.ABANDONED)
        self.assertTrue((claims.attempts_root(self.project)
                         / f"{attempt.attempt_id}.json").is_file())
        self.assertEqual(claims.unresolved(self.project), [])
        # after abandonment, a new attempt is allowed
        replacement = self.attempt()
        claims.begin(self.project, replacement)
        self.assertEqual(claims.load_attempt(self.project, replacement.attempt_id).state,
                         claims.PENDING)

    def test_a_confirmed_claim_cannot_be_abandoned(self):
        attempt = self.attempt()
        claims.begin(self.project, attempt)
        claims.record_outcome(self.project, attempt.attempt_id, claims.CONFIRMED)
        with self.assertRaises(LifecycleError) as raised:
            claims.abandon(self.project, attempt.attempt_id, confirm=True)
        self.assertEqual(raised.exception.code, "CLAIM_INVALID")

    def test_an_abandoned_record_is_final(self):
        attempt = self.attempt()
        claims.begin(self.project, attempt)
        claims.abandon(self.project, attempt.attempt_id, confirm=True)
        with self.assertRaises(LifecycleError) as raised:
            claims.record_outcome(self.project, attempt.attempt_id, claims.LOST)
        self.assertEqual(raised.exception.code, "CLAIM_INVALID")

    def test_a_pending_attempt_survives_a_lifecycle_update_byte_identically(self):
        from ainative.lifecycle.digest import digest_file

        self.install("standard")
        attempt = self.attempt()
        path = claims.begin(self.project, attempt)
        before = digest_file(path)
        from ainative.lifecycle import installer

        installer.install(self.project, "standard", operation="update",
                          distribution=self.distribution, source=self.source)
        self.assertEqual(digest_file(path), before,
                         "a lifecycle update touched a pending claim attempt")
        self.assertEqual(statelib.SCHEMA_VERSION,
                         statelib.load(self.project).schema_version)

    def test_the_cli_lists_inspects_and_abandons(self):
        attempt = self.attempt()
        claims.begin(self.project, attempt)
        listed = json.loads(self.cli("claim-attempt", "list", "--json").stdout)
        self.assertEqual(listed["unresolved"], [attempt.attempt_id])
        inspected = json.loads(self.cli("claim-attempt", "inspect",
                                        attempt.attempt_id, "--json").stdout)
        self.assertEqual(inspected["marker"], attempt.marker)
        refused = self.cli("claim-attempt", "abandon", attempt.attempt_id)
        self.assertEqual(refused.returncode, 2, "abandon without --confirm must refuse")
        abandoned = json.loads(self.cli("claim-attempt", "abandon", attempt.attempt_id,
                                        "--confirm", "--json").stdout)
        self.assertEqual(abandoned["state"], claims.ABANDONED)
        self.assertEqual(json.loads(self.cli("claim-attempt", "list", "--json").stdout)
                         ["unresolved"], [])


class ForgeObservation(LifecycleTestCase):
    """`forge detect|status` and the doctor extension: observe, never mutate."""

    def snapshot(self) -> dict:
        from ainative.lifecycle.digest import digest_file

        return {path.relative_to(self.project).as_posix(): digest_file(path) or ""
                for path in self.project.rglob("*") if path.is_file()}

    def remote(self, name: str, url: str) -> None:
        subprocess.run(["git", "-C", str(self.project), "remote", "add", name, url],
                       check=True, capture_output=True)

    def test_detect_resolves_a_single_hosted_remote(self):
        self.remote("origin", "git@github.com:o/r.git")
        record = json.loads(self.cli("forge", "detect", "--json").stdout)
        self.assertEqual(record["resolution"]["state"], "RESOLVED")
        self.assertEqual(record["resolution"]["authority"],
                         {"provider": "github", "project": "o/r"})

    def test_a_fork_renders_ambiguous_without_preferring_origin(self):
        self.remote("origin", "https://github.com/me/fork.git")
        self.remote("upstream", "https://github.com/org/project.git")
        completed = self.cli("forge", "detect", "--json")
        self.assertEqual(completed.returncode, 0, "detection is diagnostic, not a failure")
        record = json.loads(completed.stdout)
        self.assertEqual(record["resolution"]["state"], "AMBIGUOUS")
        self.assertEqual([item["name"] for item in record["remotes"]],
                         ["origin", "upstream"])
        self.assertIn("Resolution: AMBIGUOUS", self.cli("forge", "detect").stdout)

    def test_an_unknown_host_is_unavailable_not_guessed(self):
        self.remote("origin", "https://git.example.com/o/r.git")
        record = json.loads(self.cli("forge", "detect", "--json").stdout)
        self.assertEqual(record["remotes"][0]["provider"], "unknown")
        self.assertEqual(record["resolution"]["state"], "UNAVAILABLE")

    def test_forge_status_reports_features_and_claim_attempts(self):
        self.install("standard")
        claims.begin(self.project, claims.new_attempt(
            authority=forgelib.WorkAuthorityRef(provider="github", project="o/r"),
            item="42", principal=claims.principal("github", "alice")))
        record = json.loads(self.cli("forge", "status", "--json").stdout)
        self.assertEqual(record["features"]["active"], ["forge-github"])
        self.assertEqual(len(record["claim_attempts"]["unresolved"]), 1)

    def test_observation_commands_never_write(self):
        self.install("standard")
        self.remote("origin", "git@github.com:o/r.git")
        before = self.snapshot()
        self.cli("forge", "detect")
        self.cli("forge", "status")
        self.cli("doctor")
        self.assertEqual(self.snapshot(), before,
                         "an observation command touched the project")

    def test_doctor_reports_features_forge_and_claims(self):
        self.install("standard")
        self.remote("origin", "https://gitlab.com/g/p.git")
        record = json.loads(self.cli("doctor", "--json").stdout)
        self.assertEqual(record["features"]["active"], ["forge-github"])
        self.assertEqual(record["forge"]["resolution"]["authority"]["provider"], "gitlab")
        self.assertEqual(record["claim_attempts"]["journal"], "ok")
        self.assertEqual(record["claim_attempts"]["unresolved"], [])

    def test_a_legacy_gitlab_remote_keeps_the_default_with_a_warning(self):
        """Scenario M: the choice stays explicit; the doctor says so."""

        self.install("standard")
        self.remote("origin", "https://gitlab.com/g/p.git")
        path = statelib.state_path(self.project)
        record = json.loads(path.read_text(encoding="utf-8"))
        record["schema_version"] = 1
        record.pop("active_features", None)
        statelib.write_atomic(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
        text = self.cli("doctor").stdout
        self.assertIn("feature switch forge-gitlab", text)
        reported = json.loads(self.cli("doctor", "--json").stdout)
        self.assertEqual(reported["features"]["active"], ["forge-github"])
        self.assertTrue(reported["features"]["projected_from_legacy"])


if __name__ == "__main__":
    unittest.main()
