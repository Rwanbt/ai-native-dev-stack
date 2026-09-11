"""Record bounded, non-secret Obsidian REST identity observations for MV-00.1."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
from pathlib import Path
import socket
import ssl
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


DEFAULT_ENDPOINTS: Final = ("https://127.0.0.1:27124", "http://127.0.0.1:27123")


class RestIdentityBinding(StrEnum):
    """Only VERIFIED permits sensitive REST use; all other values fail closed."""

    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EndpointObservation:
    endpoint: str
    reachable: bool
    status_code: int | None
    redirect_location: str | None
    error: str | None


@dataclass(frozen=True)
class RestFeasibilityReport:
    schema_version: int
    recorded_at: str
    expected_vault_identity: str | None
    identity_binding: RestIdentityBinding
    sensitive_rest_available: bool
    observations: tuple[EndpointObservation, ...]
    reason: str
    instance_identity: str | None = None


class NoRedirectHandler(HTTPRedirectHandler):
    """A redirect is an observation, never an automatically followed request."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def endpoint_candidates(endpoint_override: str | None) -> tuple[str, ...]:
    """Return explicit candidates without treating process environment as authority."""

    if endpoint_override:
        return (endpoint_override,)
    return DEFAULT_ENDPOINTS


def is_loopback_endpoint(endpoint: str) -> bool:
    """Reject remote endpoints before connecting; local DNS names are not accepted."""

    parsed = urlparse(endpoint)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "::1"}


def request_endpoint(endpoint: str, timeout_seconds: float) -> EndpointObservation:
    """Perform one unauthenticated root request and retain only safe metadata."""

    if not is_loopback_endpoint(endpoint):
        return EndpointObservation(endpoint, False, None, None, "non-loopback endpoint denied")
    request = Request(endpoint, method="GET", headers={"Accept": "application/json"})
    opener = build_opener(NoRedirectHandler(), HTTPSHandler(context=_ssl_context(endpoint)))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            return EndpointObservation(endpoint, True, response.status, None, None)
    except HTTPError as error:
        return EndpointObservation(endpoint, True, error.code, error.headers.get("Location"), None)
    except (URLError, TimeoutError, socket.timeout, ssl.SSLError) as error:
        return EndpointObservation(endpoint, False, None, None, type(error).__name__)


def _ssl_context(endpoint: str) -> ssl.SSLContext | None:
    """The local plugin may use a self-signed certificate; this never applies remotely."""

    if urlparse(endpoint).scheme != "https":
        return None
    return ssl._create_unverified_context()  # noqa: SLF001 - local-only probe


def classify(observations: tuple[EndpointObservation, ...], expected_vault_identity: str | None) -> tuple[RestIdentityBinding, str]:
    """Do not infer a vault identity from reachability, HTTP status, or a shared port."""

    if any(item.redirect_location for item in observations):
        return RestIdentityBinding.NONE, "redirect observed; endpoint boundary is not established"
    if not any(item.reachable for item in observations):
        return RestIdentityBinding.UNKNOWN, "no candidate endpoint answered"
    if expected_vault_identity:
        return RestIdentityBinding.UNKNOWN, "endpoint answered but exposed no verified vault identity"
    return RestIdentityBinding.UNKNOWN, "no expected vault identity was supplied"


def run(endpoint_override: str | None, expected_vault_identity: str | None, timeout_seconds: float) -> RestFeasibilityReport:
    """Collect observations; this probe deliberately cannot upgrade an unknown identity."""

    observations = tuple(request_endpoint(endpoint, timeout_seconds) for endpoint in endpoint_candidates(endpoint_override))
    identity_binding, reason = classify(observations, expected_vault_identity)
    return RestFeasibilityReport(
        schema_version=1,
        recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        expected_vault_identity=expected_vault_identity,
        identity_binding=identity_binding,
        sensitive_rest_available=identity_binding is RestIdentityBinding.VERIFIED,
        observations=observations,
        reason=reason,
        instance_identity=None,  # set only by a qualifying authenticated probe; never inferred here
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", help="single loopback endpoint to probe")
    parser.add_argument("--expected-vault-identity")
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    report = run(args.endpoint, args.expected_vault_identity, args.timeout_seconds)
    encoded = json.dumps(asdict(report), sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
