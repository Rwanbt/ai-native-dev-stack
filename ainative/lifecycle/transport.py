"""HTTP transport for release metadata and artifacts: credential confinement.

urllib follows redirects by copying every request header - `Authorization`
included - to the redirect target, whatever its origin. A release endpoint that
answers `302` can therefore hand the user's token to any host, and a custom
source can name an artifact URL that the fetcher will authenticate. Both are
credential exfiltration behind a legitimate-looking request, and neither shows
up in a test that only walks the happy path (PR-0A, issue #158).

This module owns one rule and enforces it on every hop: a credential is sent
only to the origin it belongs to. Everything else follows from the two kinds of
request the update path makes:

* **metadata** - the release document. It must stay on its own origin; a
  redirect away from it is refused outright.
* **artifact** - the release bytes. They may legitimately live on a CDN (GitHub
  answers `302` to `objects.githubusercontent.com`), so a cross-origin redirect
  is followed - anonymously. The credential is recomputed per hop, so it can
  never cross an origin boundary.

HTTPS is mandatory on every hop; an `https -> http` downgrade is refused, and a
URL carrying userinfo is refused. Redirects and bodies are bounded: an update
check runs in the background of a status command and must fail fast, never
loop, and never read an unbounded body.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .errors import LifecycleError

NETWORK_TIMEOUT_SECONDS = 5

# A metadata document and an artifact pass through at most one legitimately
# chained redirect today (API -> object storage); five leaves room for a mirror
# without becoming a way to make the updater walk an arbitrary chain.
MAX_REDIRECTS = 5

USER_AGENT = "ainative-lifecycle"
ACCEPT_GITHUB_JSON = "application/vnd.github+json"
ACCEPT_OCTET_STREAM = "application/octet-stream"

GITHUB_PROVIDER = "github"
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
ANONYMOUS_PROVIDER = "anonymous-url"
ENVIRONMENT_CREDENTIAL_SOURCE = "environment"

METADATA = "metadata"
ARTIFACT = "artifact"
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_HTTPS_PORT = 443


@dataclass(frozen=True)
class ReleaseProviderEndpointConfig:
    """Where a provider's requests go, and where its credential may go.

    `auth_origin` is the only origin ever allowed to receive a credential, and
    it is configuration - never derived from the URL being fetched, or a
    malicious response could widen its own trust. `credential_source` names
    where the credential comes from and is resolved by the provider, not here.
    An endpoint with `auth_origin=None` is anonymous by construction: no
    credential can be attached whatever the environment holds.
    """

    provider: str
    api_base_url: str
    auth_origin: str | None = None
    api_version: str = ""
    credential_source: str = ""


GITHUB_ENDPOINT = ReleaseProviderEndpointConfig(
    provider=GITHUB_PROVIDER,
    api_base_url=GITHUB_API_BASE_URL,
    auth_origin=GITHUB_API_BASE_URL,
    api_version=GITHUB_API_VERSION,
    credential_source=ENVIRONMENT_CREDENTIAL_SOURCE,
)


def anonymous_endpoint(url: str) -> ReleaseProviderEndpointConfig:
    """The anonymous selector's endpoint: a URL, and no credential, ever."""

    return ReleaseProviderEndpointConfig(provider=ANONYMOUS_PROVIDER, api_base_url=url)


def _origin_of(url: str) -> str:
    """`https://host[:port]` for a request URL, or a refusal.

    A refused URL never reaches a socket, so a configuration mistake fails as a
    message rather than as a request to the wrong place.
    """

    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"release URL is unreadable: {error}") from error
    if parts.scheme != "https":
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"refusing a non-HTTPS release URL: {url}")
    if parts.username is not None or parts.password is not None:
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             "refusing a release URL carrying embedded credentials")
    host = parts.hostname
    if not host:
        raise LifecycleError("UPDATE_CHECK_FAILED", f"release URL names no host: {url}")
    if ":" in host:
        host = f"[{host}]"
    if port is not None and port != _HTTPS_PORT:
        return f"https://{host}:{port}"
    return f"https://{host}"


def _may_receive(endpoint: ReleaseProviderEndpointConfig, origin: str) -> bool:
    """True only for the configured credential origin. A bad config never grants."""

    if endpoint.auth_origin is None:
        return False
    try:
        return _origin_of(endpoint.auth_origin) == origin
    except LifecycleError:
        return False


def _request_headers(endpoint: ReleaseProviderEndpointConfig, origin: str, *,
                     accept: str, token: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if endpoint.api_version:
        headers["X-GitHub-Api-Version"] = endpoint.api_version
    if token and _may_receive(endpoint, origin):
        headers["Authorization"] = f"Bearer {token}"
    return headers


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never redirects. `get()` follows the chain itself, one policy-checked hop
    at a time; urllib's handler would copy `Authorization` to the target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _send(request: urllib.request.Request):
    """One HTTP exchange, never a redirect followed by urllib."""

    opener = urllib.request.build_opener(_NoRedirectHandler)
    return opener.open(request, timeout=NETWORK_TIMEOUT_SECONDS)


def _redirect_target(current: str, error: urllib.error.HTTPError) -> str:
    headers = error.headers
    location = headers.get("Location") if headers is not None else None
    if not location:
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             "release source redirected without a Location header")
    target = urllib.parse.urljoin(current, location)
    _origin_of(target)     # refuses non-HTTPS, userinfo, or a missing host
    return target


def _http_refusal(error: urllib.error.HTTPError) -> LifecycleError:
    # The status is the diagnosis; the message never echoes headers.
    detail = ("the release source rate-limited this check; set GITHUB_TOKEN "
              "or GH_TOKEN to raise the limit"
              if error.code in (403, 429)
              else f"the release source answered HTTP {error.code}")
    return LifecycleError("UPDATE_CHECK_FAILED", detail)


def get(url: str, *, limit: int, endpoint: ReleaseProviderEndpointConfig,
        kind: str, accept: str, token: str = "") -> bytes:
    """Fetch release metadata or artifact bytes under the confinement rule.

    Metadata may only redirect within its own origin. Artifacts may redirect
    across origins, and every hop recomputes its headers, so a credential is
    attached exactly at `auth_origin` - the CDN hop after a GitHub `302` is
    anonymous by construction, not by a special case.
    """

    if kind not in (METADATA, ARTIFACT):
        raise ValueError(f"unknown release request kind {kind!r}")
    metadata_origin = _origin_of(url) if kind == METADATA else None
    current = url
    headers = _request_headers(endpoint, _origin_of(current), accept=accept, token=token)

    for _hop in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(current, headers=dict(headers), method="GET")
        try:
            with _send(request) as response:
                payload = response.read(limit + 1)
        except urllib.error.HTTPError as error:
            if error.code not in _REDIRECT_CODES:
                raise _http_refusal(error) from error
            target = _redirect_target(current, error)
            if kind == METADATA and _origin_of(target) != metadata_origin:
                raise LifecycleError(
                    "UPDATE_CHECK_FAILED",
                    f"release metadata redirects to another origin ({_origin_of(target)}); "
                    "refusing to follow") from error
            current = target
            headers = _request_headers(endpoint, _origin_of(current), accept=accept,
                                       token=token)
            continue
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"cannot reach the release source: {error}") from error
        if len(payload) > limit:
            raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                                 f"response from {current} exceeds {limit} bytes")
        return payload

    raise LifecycleError(
        "UPDATE_CHECK_FAILED",
        f"release source redirects more than {MAX_REDIRECTS} times; refusing to follow")


__all__ = [
    "ReleaseProviderEndpointConfig", "GITHUB_ENDPOINT", "anonymous_endpoint",
    "get", "METADATA", "ARTIFACT", "MAX_REDIRECTS", "NETWORK_TIMEOUT_SECONDS",
    "USER_AGENT", "ACCEPT_GITHUB_JSON", "ACCEPT_OCTET_STREAM",
    "GITHUB_PROVIDER", "GITHUB_API_BASE_URL", "GITHUB_API_VERSION",
    "ANONYMOUS_PROVIDER", "ENVIRONMENT_CREDENTIAL_SOURCE",
]
