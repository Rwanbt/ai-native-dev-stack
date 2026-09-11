from __future__ import annotations

from unittest.mock import patch
import unittest

from scripts.mv00.rest_feasibility import (
    EndpointObservation,
    RestIdentityBinding,
    classify,
    endpoint_candidates,
    is_loopback_endpoint,
    request_endpoint,
    run,
)


class RestFeasibilityTests(unittest.TestCase):
    def test_endpoint_candidates_uses_defaults_only_without_override(self):
        self.assertEqual(
            ("https://127.0.0.1:27124", "http://127.0.0.1:27123"),
            endpoint_candidates(None),
        )

    def test_loopback_validation_rejects_remote_and_hostname_endpoints(self):
        self.assertTrue(is_loopback_endpoint("https://127.0.0.1:27124"))
        self.assertTrue(is_loopback_endpoint("http://[::1]:27123"))
        self.assertFalse(is_loopback_endpoint("https://localhost:27124"))
        self.assertFalse(is_loopback_endpoint("https://example.test"))

    def test_reachable_endpoint_without_identity_stays_unknown(self):
        observation = EndpointObservation("https://127.0.0.1:27124", True, 200, None, None)
        self.assertEqual(
            (RestIdentityBinding.UNKNOWN, "endpoint answered but exposed no verified vault identity"),
            classify((observation,), "company-a"),
        )

    def test_redirect_is_not_followed_and_denies_binding(self):
        observation = EndpointObservation("https://127.0.0.1:27124", True, 302, "https://other.test", None)
        binding, reason = classify((observation,), "company-a")
        self.assertEqual(RestIdentityBinding.NONE, binding)
        self.assertIn("redirect", reason)

    def test_unreachable_endpoints_stay_unknown(self):
        observation = EndpointObservation("https://127.0.0.1:27124", False, None, None, "URLError")
        self.assertEqual(
            (RestIdentityBinding.UNKNOWN, "no candidate endpoint answered"),
            classify((observation,), "company-a"),
        )

    @patch("scripts.mv00.rest_feasibility.build_opener")
    def test_request_passes_tls_context_to_handler_not_opener_open(self, build_opener):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                return False

        class Opener:
            def open(self, request, timeout):
                self.timeout = timeout
                return Response()

        opener = Opener()
        build_opener.return_value = opener
        observation = request_endpoint("http://127.0.0.1:27123", 1.0)
        self.assertTrue(observation.reachable)
        self.assertEqual(1.0, opener.timeout)

    @patch("scripts.mv00.rest_feasibility.request_endpoint")
    def test_run_never_enables_sensitive_rest_from_reachability(self, request_endpoint):
        request_endpoint.return_value = EndpointObservation("https://127.0.0.1:27124", True, 200, None, None)
        report = run("https://127.0.0.1:27124", "company-a", 1.0)
        self.assertEqual(RestIdentityBinding.UNKNOWN, report.identity_binding)
        self.assertFalse(report.sensitive_rest_available)


if __name__ == "__main__":
    unittest.main()
