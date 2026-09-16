"""Provider-neutral helpers behave identically for GitHub and GitLab (§74).

The claim grammar, the Work Authority resolver and the release version policy
are parameterized by provider. Nothing may behave differently because the
provider word is `gitlab` instead of `github`: same identity shape, same
normalization, same selection rules.
"""

from __future__ import annotations

import unittest

from ainative import claims
from ainative import forge as forgelib
from ainative.lifecycle import release_v3
from ainative.lifecycle.errors import LifecycleError

PROVIDERS = ("github", "gitlab")


class ContractPurity(unittest.TestCase):

    def test_canonical_identities_share_one_shape_across_providers(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.assertEqual(claims.principal(provider, "actor-1"),
                                 f"{provider}:principal:actor-1")
                self.assertEqual(claims.event_identifier(provider, "note", "42"),
                                 f"{provider}:note:42")
                self.assertEqual(claims.event_identifier(provider, "comment", "42"),
                                 f"{provider}:comment:42")

    def test_remote_reading_understands_both_hosted_forges(self):
        github = forgelib.ObservedRemote(name="origin",
                                         url="git@github.com:org/project.git")
        gitlab = forgelib.ObservedRemote(name="origin",
                                         url="https://gitlab.com/org/sub/project.git")
        self.assertEqual(github.provider, "github")
        self.assertEqual(github.identity, "org/project")
        self.assertEqual(gitlab.provider, "gitlab")
        self.assertEqual(gitlab.identity, "org/sub/project")
        for remote in (github, gitlab):
            resolved = forgelib.resolve_observed_work_authority(remotes=(remote,))
            self.assertEqual(resolved.provider, remote.provider)
            self.assertEqual(resolved.project, remote.identity)

    def test_the_version_policy_is_provider_independent(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.assertEqual(release_v3.canonical_version("v2.5.0"), "2.5.0")
                with self.assertRaises(LifecycleError) as raised:
                    release_v3.canonical_version("2.5.0+build1")
                self.assertEqual(raised.exception.code,
                                 "RELEASE_BUILD_METADATA_UNSUPPORTED")
                candidates = (
                    release_v3.ReleaseCandidate(version="2.5.0",
                                                identity=f"{provider}:v2.5.0"),
                    release_v3.ReleaseCandidate(version="2.5.0-rc.1",
                                                identity=f"{provider}:v2.5.0-rc.1"),
                )
                chosen = release_v3.select_candidate(
                    release_v3.EnumerationResult(candidates, complete=True),
                    release_v3.ReleaseQuery("stable"))
                self.assertEqual(chosen.version, "2.5.0")


if __name__ == "__main__":
    unittest.main()
