# Contract tests for skills/implementation-economy/SKILL.md.
#
# These tests pin normative invariants, never prose. They fail when a
# required guarantee disappears and stay green across rewording.

from __future__ import annotations

import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / 'skills' / 'implementation-economy' / 'SKILL.md'

FRONTMATTER_FORBIDDEN = ('applies_to:', 'excludes:', 'version:', 'priority:', 'mode:')

EXCLUSIONS = ('requirements definition', 'planning', 'architecture design', 'architecture review', 'security review', 'code review', 'audit', 'research')

HARD_BOUNDARY_TOKENS = ('authentication', 'authorization', 'validation', 'transactions', 'timeouts', 'cancellation', 'audit', 'accessibility')

FOOTPRINT_LADDER = ('1. new ownership boundary;', '2. new source of truth;', '3. new persistent state / persistence mechanism;', '4. new public surface;', '5. new configuration surface;', '6. new dependency;', '7. new abstraction;', '8. new source file;', '9. LOC.')

NOVELTY_TRIGGERS = ('- new dependency:', '- new configuration surface:', '- new source of truth or persistence:', '- new execution or lifecycle mechanism:')

DELETION_DYNAMIC = ('plugin', 'reflection', 'FFI', 'public APIs', 'DI')



class ImplementationEconomySkillContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        text = SKILL.read_text(encoding='utf-8')
        assert text.startswith('---' + chr(10)), 'frontmatter must open the file'
        _, cls.frontmatter, cls.body = text.split('---' + chr(10), 2)
        cls.lines = cls.body.splitlines()

    def test_skill_exists(self) -> None:
        self.assertTrue(SKILL.is_file())

    def test_frontmatter_uses_supported_schema(self) -> None:
        self.assertIn('name: implementation-economy', self.frontmatter)
        self.assertIn('origin: ai-native-dev-stack', self.frontmatter)
        self.assertIn('description: |', self.frontmatter)
        for key in FRONTMATTER_FORBIDDEN:
            self.assertNotIn(key, self.frontmatter)

    def test_stop_applicability_barrier_exists(self) -> None:
        head = chr(10).join(self.lines[:30])
        self.assertIn('STOP', head)
        self.assertIn('applicability check', head.lower())
        stop = self.body.index('STOP')
        first_stage = self.body.index('## 1.')
        self.assertLess(stop, first_stage)

    def test_required_exclusions_are_present(self) -> None:
        for excluded in EXCLUSIONS:
            with self.subTest(excluded=excluded):
                self.assertIn(excluded, self.body)

    def test_ownership_precedes_economy(self) -> None:
        owner = self.body.index('## 2. Establish the correct owner')
        mechanism = self.body.index('## 4. Compare ownership-valid mechanisms')
        self.assertLess(owner, mechanism)
        self.assertIn('accepted behavior -> correct owner -> implementation', self.body)

    def test_hard_boundaries_are_preserved(self) -> None:
        for token in HARD_BOUNDARY_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, self.body)

    def test_minimal_new_footprint_order_is_exact(self) -> None:
        positions = [self.body.index(item) for item in FOOTPRINT_LADDER]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(set(positions)), len(FOOTPRINT_LADDER))

    def test_required_owner_cannot_be_optimized_away(self) -> None:
        self.assertIn('required owner is never a cost Economy may optimize away', self.body)

    def test_legitimate_abstraction_rule_preserves_single_consumer(self) -> None:
        self.assertIn('A single consumer is neither proof of necessity nor proof of', self.body)

    def test_residual_novelty_is_limited_to_four_trigger_classes(self) -> None:
        start = self.body.index('## 6. Apply the residual Novelty Gate')
        end = self.body.index('## 7. Implement the cohesive solution')
        section = self.body[start:end]
        for trigger in NOVELTY_TRIGGERS:
            self.assertIn(trigger, section)
        bullets = [line for line in section.splitlines() if line.startswith('- new ')]
        self.assertEqual(len(bullets), 4)

    def test_scope_firewall_is_fail_closed(self) -> None:
        self.assertIn('Accepted explicit scope outranks Economy', self.body)
        self.assertIn('never permission to widen scope', self.body)

    def test_preexisting_deletion_is_fail_closed(self) -> None:
        self.assertIn('explicit removal scope', self.body)
        self.assertIn('mechanically closed reachability', self.body)
        self.assertIn('never exhaustive', self.body)
        for dynamic in DELETION_DYNAMIC:
            with self.subTest(dynamic=dynamic):
                self.assertIn(dynamic, self.body)

    def test_work_plane_reconciliation_is_present(self) -> None:
        self.assertIn('Verified Work Plane', self.body)
        self.assertIn('edit authority artifacts ad hoc', self.body)

    def test_one_simplification_pass_is_explicit(self) -> None:
        self.assertIn('ONE scoped simplification pass', self.body)
        self.assertIn('same focused verification again', self.body)

    def test_no_economy_runtime_or_mode_is_defined(self) -> None:
        for token in ('AI_NATIVE_ECONOMY', 'runtime mode', 'global mode'):
            self.assertNotIn(token, self.body)


if __name__ == '__main__':
    unittest.main(verbosity=2)

