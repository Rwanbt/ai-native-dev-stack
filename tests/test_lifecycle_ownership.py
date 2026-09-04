"""Ownership, user modifications, and external configuration.

The single question behind every test here: can any operation destroy something
the user wrote? The answer must be no for a managed file they edited, for their
own files, for their Verified history, and for the parts of a config file the
stack does not own.
"""

from __future__ import annotations

import unittest

from tests.lifecycle_support import LifecycleTestCase, build_distribution_tree
from ainative.lifecycle import digest as digestlib
from ainative.lifecycle import external, manifest as manifestlib
from ainative.lifecycle import planner as plannerlib
from ainative.lifecycle import recovery, source as sourcelib


class ManagedFileOwnership(LifecycleTestCase):

    def test_a_user_edited_managed_file_is_never_replaced_by_an_install(self):
        self.install("standard")
        edited = "#!/bin/sh\n# my own hook\n"
        self.write("tools/ai_docs/run_hook.sh", edited)
        self.install("standard")
        self.assertEqual(self.read("tools/ai_docs/run_hook.sh"), edited)

    def test_a_user_edited_managed_file_is_never_removed_by_an_uninstall(self):
        self.install("standard")
        self.write(".claude/skills/demo-skill/SKILL.md", "# mine now\n")
        result = self.uninstall()
        self.assertTrue(self.exists(".claude/skills/demo-skill/SKILL.md"))
        self.assertEqual(self.read(".claude/skills/demo-skill/SKILL.md"), "# mine now\n")
        self.assertIn(".claude/skills/demo-skill/SKILL.md", result.preserved_user_modified)

    def test_an_edit_survives_install_update_downgrade_and_uninstall(self):
        """The fixture the plan asks for: one edit, four operations, still there."""

        self.install("standard")
        edited = "# generate_all.py — my version\n"
        self.write("tools/ai_docs/generate_all.py", edited)

        self.switch("verified")
        self.assertEqual(self.read("tools/ai_docs/generate_all.py"), edited)

        newer = build_distribution_tree(self.root / "dist-v2", "1.1.0")
        source_v2 = sourcelib.DistributionSource(root=newer.resolve(), origin="test",
                                                 version="1.1.0")
        from ainative.lifecycle import installer

        installer.install(self.project, "verified", operation="update",
                          distribution=self.distribution, source=source_v2)
        self.assertEqual(self.read("tools/ai_docs/generate_all.py"), edited)

        installer.install(self.project, "standard", operation="profile-switch",
                          distribution=self.distribution, source=source_v2)
        self.assertEqual(self.read("tools/ai_docs/generate_all.py"), edited)

        self.uninstall()
        self.assertEqual(self.read("tools/ai_docs/generate_all.py"), edited)

    def test_a_file_the_upstream_dropped_is_pruned_only_when_unchanged(self):
        extended = build_distribution_tree(self.root / "dist-extra", "1.0.0",
                                           extra_skill="going-away")
        source_extra = sourcelib.DistributionSource(root=extended.resolve(), origin="test",
                                                    version="1.0.0")
        from ainative.lifecycle import installer

        installer.install(self.project, "standard", distribution=self.distribution,
                          source=source_extra)
        self.assertTrue(self.exists(".claude/skills/going-away/SKILL.md"))

        # The next release no longer ships it. One copy is untouched, one edited.
        self.write(".agents/skills/going-away/SKILL.md", "# I edited this\n")
        installer.install(self.project, "standard", operation="update",
                          distribution=self.distribution, source=self.source)

        self.assertFalse(self.exists(".claude/skills/going-away/SKILL.md"),
                         "an unchanged file removed upstream survived")
        self.assertEqual(self.read(".agents/skills/going-away/SKILL.md"), "# I edited this\n",
                         "an edited file removed upstream was deleted")

    def test_a_pre_existing_unmanaged_file_is_reported_not_overwritten(self):
        self.write("AGENTS.md", "# my own AGENTS.md\n")
        result = self.install("standard")
        self.assertEqual(self.read("AGENTS.md"), "# my own AGENTS.md\n")
        conflicts = [c.path for c in result.plan.changes
                     if c.action == plannerlib.CONFLICT]
        self.assertIn("AGENTS.md", conflicts)

    def test_user_owned_template_copy_is_never_overwritten_or_removed(self):
        self.install("standard")
        self.write("tools/ai_docs/config.sh", "VAULT=/my/vault\n")
        self.install("standard")
        self.assertEqual(self.read("tools/ai_docs/config.sh"), "VAULT=/my/vault\n")
        self.uninstall()
        self.assertEqual(self.read("tools/ai_docs/config.sh"), "VAULT=/my/vault\n")

    def test_state_records_a_digest_for_every_managed_file(self):
        self.install("verified")
        for entry in self.state().managed_files:
            if entry.kind != "file":
                continue
            self.assertIsNotNone(entry.digest_at_install,
                                 f"{entry.path} was recorded without an install digest")
            status = digestlib.classify(self.project / entry.path, entry.digest_at_install)
            self.assertEqual(status, digestlib.UNCHANGED, entry.path)


class ExternalConfiguration(LifecycleTestCase):

    UNRELATED = ("# project ignores\n"
                 "*.log\n"
                 "build/\n"
                 "\n"
                 "# my own section\n"
                 "secrets.env\n")

    def test_install_adds_only_a_delimited_region(self):
        self.write(".gitignore", self.UNRELATED)
        self.install("standard")
        content = self.read(".gitignore")
        self.assertTrue(content.startswith(self.UNRELATED),
                        "the installer rewrote content it does not own")
        self.assertIn("tools/ai_docs/config.sh", content)

    def test_uninstall_restores_the_file_byte_for_byte(self):
        self.write(".gitignore", self.UNRELATED)
        self.install("standard")
        self.uninstall()
        self.assertEqual(self.read(".gitignore"), self.UNRELATED)

    def test_user_lines_added_after_the_block_survive_uninstall(self):
        self.write(".gitignore", self.UNRELATED)
        self.install("standard")
        self.write(".gitignore", self.read(".gitignore") + "added-later.txt\n")
        self.uninstall()
        self.assertEqual(self.read(".gitignore"), self.UNRELATED + "added-later.txt\n")

    def test_a_file_the_stack_created_alone_is_removed_entirely(self):
        self.install("standard")
        self.assertTrue(self.exists(".gitignore"))
        self.uninstall()
        self.assertFalse(self.exists(".gitignore"),
                         "a file whose only content was the managed block survived")

    def test_reinstalling_the_block_is_idempotent(self):
        self.write(".gitignore", self.UNRELATED)
        self.install("standard")
        first = self.read(".gitignore")
        self.install("standard")
        self.assertEqual(self.read(".gitignore"), first)

    def test_a_second_managed_block_is_reported_as_duplicate(self):
        self.write(".gitignore", self.UNRELATED)
        self.install("standard")
        component = self.distribution.component("gitignore-entry")
        spec = plannerlib.block_spec(component)
        self.write(".gitignore", self.read(".gitignore") + spec.render())
        diagnosis = recovery.diagnose(self.project, distribution=self.distribution)
        statuses = {item["path"]: item["status"] for item in diagnosis.findings}
        self.assertEqual(statuses[".gitignore"], recovery.DUPLICATE)

    def test_block_apply_and_remove_are_exact_inverses(self):
        spec = external.BlockSpec("marker", "#", ("a", "b"))
        path = self.write("config", self.UNRELATED)
        applied, changed = external.apply(path, spec)
        self.assertTrue(changed)
        path.write_text(applied, encoding="utf-8")
        removed, changed = external.remove(path, spec)
        self.assertTrue(changed)
        self.assertEqual(removed, self.UNRELATED)


class OwnershipDeclarations(unittest.TestCase):

    def test_every_declared_component_uses_a_known_ownership_class(self):
        distribution = manifestlib.load()
        for identifier, component in distribution.components.items():
            self.assertIn(component.ownership, manifestlib.OWNERSHIPS, identifier)
            self.assertIn(component.kind, manifestlib.KINDS, identifier)

    def test_verified_history_is_declared_user_data(self):
        distribution = manifestlib.load()
        component = distribution.component("verified-data")
        self.assertEqual(component.ownership, manifestlib.USER_DATA)
        self.assertEqual(component.kind, manifestlib.KIND_DATA_ROOT)
        self.assertIn(".ai-native/trust", component.paths)
        self.assertIn(".ai-native/work", component.paths)

    def test_verified_extends_standard_without_restating_it(self):
        distribution = manifestlib.load()
        standard = set(distribution.profile("standard").components)
        verified_own = set(distribution.profile("verified").components)
        self.assertFalse(standard & verified_own,
                         "the verified profile restates a standard component")
        effective = set(distribution.effective_component_ids("verified"))
        self.assertTrue(standard <= effective)


if __name__ == "__main__":
    unittest.main()
