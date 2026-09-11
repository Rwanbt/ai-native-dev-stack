import unittest

from scripts.mv00.git_transport import inspect


class GitTransportTests(unittest.TestCase):
    def test_inherited_transport_variables_keep_sensitive_transfer_unavailable(self):
        report = inspect({"GIT_SSH_COMMAND": "custom", "HTTPS_PROXY": "proxy"})
        self.assertEqual(("GIT_SSH_COMMAND", "HTTPS_PROXY"), report.inherited_variables)
        self.assertFalse(report.transport_qualified)
        self.assertFalse(report.sensitive_transfer_available)

    def test_empty_environment_is_not_a_qualification(self):
        report = inspect({})
        self.assertEqual((), report.inherited_variables)
        self.assertFalse(report.transport_qualified)


if __name__ == "__main__":
    unittest.main()
