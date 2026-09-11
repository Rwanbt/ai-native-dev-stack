import unittest


FAULT_MATRIX = {
    "launcher loss before phase B": ("test_multivault_sensitive_launch", "launcher_loss"),
    "runtime authority loss before phase B": ("test_multivault_sensitive_launch", "runtime_authority_loss"),
    "abrupt authority revocation invalidates handles": ("test_multivault_runtime_authority", "revoke_all"),
    "forged or foreign handle": ("test_multivault_runtime_authority", "forged"),
    "foreign authority handle at REST": ("test_multivault_rest_broker", "foreign_authority"),
    "vault root replaced": ("test_multivault_vault_root_integration", "replaced_root"),
    "junction swap": ("test_multivault_vault_root_integration", "junction_swap"),
    "provider principal drift": ("test_multivault_sensitive_launch", "provider_changes"),
    "model drift": ("test_multivault_sensitive_launch", "model_changes"),
    "endpoint drift": ("test_multivault_sensitive_launch", "endpoint_changes"),
    "auth store drift": ("test_multivault_sensitive_launch", "auth_store_changes"),
    "CLAUDE.md appears between phases": ("test_multivault_sensitive_launch", "claude_md_appears"),
    "foreign MCP caller": ("test_multivault_mcp_adapter", "foreign"),
    "semantic egress drift": ("test_multivault_semantic", "changed_status"),
    "semantic observer unavailable": ("test_multivault_semantic", "unavailable_observer"),
    "unapproved secondary remote": ("test_multivault_transfer_engine", "unapproved_secondary_remote"),
    "hooks path drift mid-push": ("test_multivault_transfer_engine", "hooks_path_change"),
    "unauthorized hook never executes": ("test_multivault_transfer_engine", "hook_is_never_executed"),
    "ambient git vector injection": ("test_multivault_git_scanner", "forbidden_ambient"),
    "submodule network attempt": ("test_multivault_transfer_engine", "submodule"),
    "LFS network attempt": ("test_multivault_transfer_engine", "lfs"),
    "canary incomplete or error": ("test_multivault_canary_sweep", "incomplete"),
    "canary real leak detection": ("test_multivault_canary_sweep", "real_leak"),
}


def discover_tests():
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_multivault_*.py")
    found = []
    for group in suite:
        for case in group:
            if isinstance(case, unittest.TestSuite):
                for inner in case:
                    found.append(inner)
            else:
                found.append(case)
    return found


class FaultInjectionMatrixTests(unittest.TestCase):
    def test_every_fault_scenario_is_executed_fail_closed(self):
        discovered = discover_tests()
        selected = []
        missing = []
        for scenario, (module, method_fragment) in FAULT_MATRIX.items():
            matches = [
                case
                for case in discovered
                if module in type(case).__module__ and method_fragment in case._testMethodName
            ]
            if not matches:
                missing.append(scenario)
            selected.extend(matches)
        self.assertEqual([], missing, f"fault scenarios without an executable test: {missing}")
        runner = unittest.TextTestRunner(verbosity=0, stream=open("nul", "w"))
        result = runner.run(unittest.TestSuite(selected))
        self.assertTrue(result.wasSuccessful(), f"fail-closed faults: {result.failures} {result.errors}")