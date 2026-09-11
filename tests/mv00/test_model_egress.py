import unittest

from scripts.mv00.model_egress import inspect


class ModelEgressTests(unittest.TestCase):
    def test_provider_surface_presence_does_not_authorize_model_egress(self):
        report = inspect({"OPENAI_API_KEY": "redacted", "OLLAMA_HOST": "local"})
        self.assertEqual(("OPENAI_API_KEY", "OLLAMA_HOST"), report.provider_surfaces_present)
        self.assertEqual("none", report.effective_model_observation)
        self.assertFalse(report.sensitive_model_available)


if __name__ == "__main__":
    unittest.main()
