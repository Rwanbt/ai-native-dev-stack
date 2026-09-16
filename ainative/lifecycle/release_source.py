"""Where a release comes from: one resolver, one conflict policy, no guessing.

`resolve_release_source()` is the only function that decides. `update`,
`update check`, `status` and `doctor` all consume it, so the answer cannot
differ between commands (ADR-0019 sections 1–3). Validation happens before
precedence: contradictory selectors are refused, never ordered, and nothing
falls back silently.

Selectors (environment):

```text
AINATIVE_UPDATE_PROVIDER=local + AINATIVE_UPDATE_LOCAL_DIR  -> local mirror
AINATIVE_UPDATE_LOCAL_DIR without provider=local            -> UPDATE_SOURCE_CONFLICT
AINATIVE_UPDATE_URL mixed with a provider/local selector    -> UPDATE_SOURCE_CONFLICT
AINATIVE_UPDATE_URL alone                                   -> anonymous release API
AINATIVE_UPDATE_PROVIDER=<name>                             -> machine config or built-in
nothing selected                                            -> machine default, else GitHub.com
```

Machine configuration lives at `~/.ai-native/release-providers.json` — machine
scope, deliberately: a cloned repository must never be able to redirect a
user's updates or name its own credential origin. The built-in names
(`github`, `gitlab`, `local`) cannot be redefined there, and V1 supports no
custom `auth_origin`: a named provider is anonymous.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import transport as transportlib
from .errors import LifecycleError

PROVIDER_ENV = "AINATIVE_UPDATE_PROVIDER"
LOCAL_SOURCE_ENV = "AINATIVE_UPDATE_LOCAL_DIR"
RELEASE_URL_ENV = "AINATIVE_UPDATE_URL"
CONFIG_RELATIVE = Path(".ai-native") / "release-providers.json"

RESERVED_PROVIDERS = ("github", "gitlab", "local")
CONFIG_SCHEMA_VERSION = 1

KIND_GITHUB = "github"
KIND_LOCAL = "local"
KIND_ANONYMOUS = "anonymous"
KIND_NAMED = "named"


@dataclass(frozen=True)
class ReleaseSource:
    """The resolved source, with the reason and the trust facts to display."""

    kind: str
    provider_name: str
    reason: str
    endpoint: transportlib.ReleaseProviderEndpointConfig | None = None
    directory: Path | None = None
    metadata_url: str | None = None

    @property
    def authenticated(self) -> bool:
        return bool(self.endpoint and self.endpoint.auth_origin is not None)

    def to_record(self) -> dict:
        return {"kind": self.kind, "provider": self.provider_name,
                "reason": self.reason,
                "authenticated": self.authenticated,
                "auth_origin": self.endpoint.auth_origin if self.endpoint else None,
                "api_base_url": self.endpoint.api_base_url if self.endpoint else None,
                "directory": str(self.directory) if self.directory else None}


def config_path(home: Path | None = None) -> Path:
    return (Path(home) if home else Path.home()) / CONFIG_RELATIVE


def load_machine_config(home: Path | None = None) -> dict:
    """The machine-scope provider configuration, validated, or {} when absent."""

    path = config_path(home)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LifecycleError("RELEASE_CONFIG_INVALID",
                             f"cannot read {path}: {error}") from error
    if not isinstance(payload, dict):
        raise LifecycleError("RELEASE_CONFIG_INVALID", f"{path} is not a JSON object")
    version = payload.get("schema_version")
    if version != CONFIG_SCHEMA_VERSION:
        raise LifecycleError(
            "RELEASE_CONFIG_INVALID",
            f"{path}: schema_version {version!r} is not {CONFIG_SCHEMA_VERSION}; "
            "upgrade the CLI rather than guessing")
    providers = payload.get("providers", {})
    if not isinstance(providers, dict):
        raise LifecycleError("RELEASE_CONFIG_INVALID",
                             f"{path}: providers must be an object")
    for name in providers:
        if name in RESERVED_PROVIDERS:
            raise LifecycleError(
                "RELEASE_CONFIG_INVALID",
                f"{path}: provider {name!r} is built in and cannot be redefined")
    default = payload.get("default_provider")
    if default is not None and (not isinstance(default, str) or not default.strip()):
        raise LifecycleError("RELEASE_CONFIG_INVALID",
                             f"{path}: default_provider must be a provider name")
    return payload


def _named_source(name: str, entry: object) -> ReleaseSource:
    if not isinstance(entry, dict):
        raise LifecycleError("RELEASE_CONFIG_INVALID",
                             f"provider {name!r} must be an object")
    if entry.get("auth_origin"):
        raise LifecycleError(
            "RELEASE_CONFIG_INVALID",
            f"provider {name!r}: custom auth_origin is not supported in V1; "
            "a named provider is anonymous")
    base = entry.get("api_base_url")
    if not isinstance(base, str) or not base.lower().startswith("https://"):
        raise LifecycleError("RELEASE_CONFIG_INVALID",
                             f"provider {name!r}: api_base_url must be an HTTPS URL")
    return ReleaseSource(kind=KIND_NAMED, provider_name=name,
                         endpoint=transportlib.anonymous_endpoint(base),
                         metadata_url=base.rstrip("/") + "/releases/latest",
                         reason=f"named provider {name!r} (machine configuration)")


def _builtin_github(reason: str) -> ReleaseSource:
    # Deferred: provider owns the default URL and imports this module inside
    # `build()`, so the import direction stays release_source -> provider.
    from . import provider as providerlib

    return ReleaseSource(kind=KIND_GITHUB, provider_name="github",
                         endpoint=transportlib.GITHUB_ENDPOINT,
                         metadata_url=providerlib.DEFAULT_RELEASE_URL,
                         reason=reason)


def resolve_release_source(environ=None, home: Path | None = None) -> ReleaseSource:
    """The one source decision. Conflicts refuse; nothing is ordered silently."""

    environment = dict(os.environ if environ is None else environ)
    config = load_machine_config(home)

    provider = (environment.get(PROVIDER_ENV) or "").strip().lower()
    local_dir = (environment.get(LOCAL_SOURCE_ENV) or "").strip()
    url = (environment.get(RELEASE_URL_ENV) or "").strip()
    _reject_conflicts(provider=provider, local_dir=local_dir, url=url)

    if url:
        return ReleaseSource(kind=KIND_ANONYMOUS, provider_name="anonymous",
                             endpoint=transportlib.anonymous_endpoint(url),
                             metadata_url=url,
                             reason=f"anonymous release API ({RELEASE_URL_ENV})")
    if provider == "local":
        return _local_mirror(local_dir)
    if provider:
        return _selected_provider(provider, config)
    return _default_source(config)


def _reject_conflicts(*, provider: str, local_dir: str, url: str) -> None:
    if url and (provider or local_dir):
        raise LifecycleError(
            "UPDATE_SOURCE_CONFLICT",
            f"{RELEASE_URL_ENV} cannot be combined with {PROVIDER_ENV}/"
            f"{LOCAL_SOURCE_ENV}; declare exactly one source",
            selectors={RELEASE_URL_ENV: url, PROVIDER_ENV: provider,
                       LOCAL_SOURCE_ENV: local_dir})
    if local_dir and provider != "local":
        raise LifecycleError(
            "UPDATE_SOURCE_CONFLICT",
            f"{LOCAL_SOURCE_ENV} requires an explicit {PROVIDER_ENV}=local; "
            "selectors are never ordered",
            selectors={LOCAL_SOURCE_ENV: local_dir, PROVIDER_ENV: provider})


def _local_mirror(local_dir: str) -> ReleaseSource:
    if not local_dir:
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"{PROVIDER_ENV}=local requires {LOCAL_SOURCE_ENV}")
    return ReleaseSource(kind=KIND_LOCAL, provider_name="local",
                         directory=Path(local_dir).expanduser(),
                         reason=f"local mirror ({LOCAL_SOURCE_ENV})")


def _selected_provider(provider: str, config: dict) -> ReleaseSource:
    if provider in ("github", "release-api"):
        return _builtin_github(f"built-in GitHub.com ({PROVIDER_ENV})")
    entry = (config.get("providers") or {}).get(provider)
    if entry is None:
        # Preserves the long-standing refusal for a name nothing declares; a
        # declared-but-malformed entry is a config problem instead.
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"unknown update provider {provider!r}")
    return _named_source(provider, entry)


def _default_source(config: dict) -> ReleaseSource:
    default = str(config.get("default_provider") or "").strip().lower()
    if default == "local":
        entry = (config.get("providers") or {}).get("local") or {}
        directory = entry.get("directory") if isinstance(entry, dict) else None
        if not isinstance(directory, str) or not directory.strip():
            raise LifecycleError(
                "RELEASE_CONFIG_INVALID",
                "default_provider 'local' requires providers.local.directory "
                "in the machine configuration")
        return ReleaseSource(kind=KIND_LOCAL, provider_name="local",
                             directory=Path(directory).expanduser(),
                             reason="machine default provider 'local'")
    if default == "github":
        return _builtin_github("machine default provider 'github'")
    if default:
        return _named_source(default, (config.get("providers") or {}).get(default))
    return _builtin_github("built-in default (GitHub.com)")


def describe(environ=None, home: Path | None = None) -> dict:
    """The source as diagnostics display it; a refusal is a state, not a crash."""

    try:
        return resolve_release_source(environ=environ, home=home).to_record()
    except LifecycleError as error:
        return {"kind": "refused", "state": error.code, "detail": error.message,
                "authenticated": False, "auth_origin": None}


def describe_lines(record: dict | None = None) -> list[str]:
    """`describe()`'s text rendering, shared by `status` and `doctor`."""

    record = record if record is not None else describe()
    if record.get("kind") == "refused":
        return ["Release source",
                f"  refused: {record.get('state')} — {record.get('detail')}"]
    lines = ["Release source",
             f"  {record.get('kind')} ({record.get('provider')}) — {record.get('reason')}"]
    suffix = f" (auth origin {record.get('auth_origin')})" if record.get("auth_origin") else ""
    lines.append(f"  authenticated: {'yes' if record.get('authenticated') else 'no'}{suffix}")
    return lines


__all__ = ["ReleaseSource", "resolve_release_source", "load_machine_config",
           "config_path", "describe", "describe_lines", "PROVIDER_ENV",
           "LOCAL_SOURCE_ENV", "RELEASE_URL_ENV", "CONFIG_RELATIVE",
           "RESERVED_PROVIDERS", "KIND_GITHUB", "KIND_LOCAL", "KIND_ANONYMOUS",
           "KIND_NAMED"]
