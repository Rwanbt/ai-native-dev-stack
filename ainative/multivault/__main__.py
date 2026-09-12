"""Multi-Vault CLI: audit query, doctor and context.

Doctor and context read only the Operator Authority Store and the repository
state; every check is fail-closed (UNKNOWN never renders as PASS) and the
context display never claims support without probe evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .audit import AuditLog
from .authority_store import AuthorityStore, AuthorityStoreCorruptError
from .binding import ALLOW_ROOT_FRESH, root_freshness
from .identity import measure_root_identity
from .status import ContextReport, doctor_report


def _doctor_checks(store_path: Path, domain: str, repository: Path, vault_root: Path | None = None) -> dict:
    checks: dict = {"canary": None}
    try:
        binding = AuthorityStore(store_path).binding(domain)
        checks["binding"] = binding is not None
    except (AuthorityStoreCorruptError, OSError):
        binding = None
        checks["binding"] = None
    checks["checkout_identity"] = (
        bool(binding.get("checkout_identity")) if binding else None
    )
    if vault_root is None:
        checks["root_freshness"] = None
    else:
        measured = measure_root_identity(str((binding or {}).get("vault", "")), vault_root)
        verdict = root_freshness(binding, measured)
        checks["root_freshness"] = verdict.decision == ALLOW_ROOT_FRESH
    from .identity import repository_checks

    try:
        checks.update(repository_checks(repository))
    except OSError:
        checks["repository"] = None
        checks["managed_hooks_path"] = None
    return checks


def _context_report(store_path: Path, domain: str, harness: str, provider_class: str, model: str, routing: str) -> ContextReport | None:
    try:
        binding = AuthorityStore(store_path).binding(domain)
    except (AuthorityStoreCorruptError, OSError):
        return None
    if not binding:
        return None
    return ContextReport(
        security_domain_id=domain,
        classification=str(binding.get("classification", "PERSONAL")),
        vault_identity=str(binding.get("vault", "")),
        checkout_identity=str(binding.get("checkout", "")),
        harness=harness,
        provider_class=provider_class,
        model=model,
        routing=routing,
        qualification="UNKNOWN",
        observation_windows=(),
        unsupported_capabilities=("probe_evidence",),
        supported=False,
    )


def _bind(args) -> int:
    """The only CLI mutation: operator intent plus real measurements, never repository data."""
    from .identity import (
        checkout_identity_digest,
        discover_checkout,
        discover_vault,
        vault_root_identity,
    )
    from .schema import SecurityClassification

    if args.classification not in SecurityClassification.__members__:
        print("bind: REFUSED unknown classification")
        return 1
    try:
        measured = vault_root_identity(discover_vault(args.vault_id, args.vault.resolve()))
        checkout_measured = checkout_identity_digest(discover_checkout(args.checkout.resolve()))
    except ValueError as error:
        print(f"bind: REFUSED {error}")
        return 1
    store = AuthorityStore(args.store)
    try:
        bindings = store.bindings()
    except AuthorityStoreCorruptError:
        print("bind: REFUSED authority store is corrupt")
        return 1
    bindings[args.domain] = {
        "vault": args.vault_id,
        "checkout": args.checkout_id,
        "classification": args.classification,
        "roots": list(args.roots),
        "root_identity": measured,
        "checkout_identity": checkout_measured,
    }
    store.replace(bindings)
    print(f"bind: RECORDED domain={args.domain} vault={args.vault_id}")
    return 0

def _pairs(values: list[str]) -> dict:
    parsed: dict = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise ValueError(f"environment entries must be KEY=VALUE: {item!r}")
        parsed[key] = value
    return parsed


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _exec_command(args) -> int:
    from functools import partial

    from .exec_composition import ExecRequest, compose_exec
    from .exec_wrapper import launch_sensitive_process
    from .harness_claude import measurement_from_probe_evidence
    from .runtime_authority import authority_from_operator_state
    from .schema import SecurityEpoch, allowed_context_envelope_from_authoritative_roots

    try:
        state = _load_json(args.operator_state)
        evidence = _load_json(args.probe_evidence)
        envelope = allowed_context_envelope_from_authoritative_roots(
            tuple(state["repository_roots"]), tuple(state["vault_memory_roots"])
        )
        epoch_fields = state["security_epoch"]
        authority = authority_from_operator_state(
            security_domain_id=args.domain,
            vault_identity=args.vault_id,
            checkout_identity=args.checkout_id,
            project_security_id=state["project_security_id"],
            classification=state["classification"],
            allowed_context_envelope=envelope,
            security_epoch=SecurityEpoch(
                args.domain,
                str(epoch_fields["epoch_counter_or_nonce"]),
                str(epoch_fields["authority_instance_generation"]),
            ),
            approved_model_egress_digest=state["approved_model_egress_digest"],
            memory_policy_digest=state["memory_policy_digest"],
            persistence_assurance_digest=state["persistence_assurance_digest"],
            execution_profile=state["execution_profile"],
            runtime_observation_policy_digest=state["runtime_observation_policy_digest"],
        )
        approved_env = _pairs(args.env)
        required_os_env = _pairs(args.os_env)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print(f"exec: REFUSED {error}")
        return 2

    workspace = args.workspace or args.checkout

    def measure():
        return measurement_from_probe_evidence(evidence)

    outcome = compose_exec(
        ExecRequest(
            store_path=args.store,
            domain=args.domain,
            vault_logical_id=args.vault_id,
            checkout_identity=args.checkout_id,
            vault_root=args.vault,
            checkout_root=args.checkout,
            workspace=workspace,
            argv=tuple(args.argv),
            approved_env=approved_env,
            required_os_env=required_os_env,
        ),
        authority=authority,
        envelope=envelope,
        measure=measure,
        spawn=partial(launch_sensitive_process, cwd=workspace),
    )
    print(f"exec: {outcome.decision} spawned={'true' if outcome.spawned else 'false'}")
    return 0 if outcome.spawned else 1


def _sync_command(args) -> int:
    from .git_authority import (
        ApprovedGitRemote,
        GitTransportPolicy,
        ObservedRepositoryIdentity,
        ObservedTransport,
        Visibility,
    )
    from .sync_composition import SyncRequest, compose_fetch, compose_push

    try:
        git_state = _load_json(args.git_state)
        observed = _load_json(args.observed)
        remote_state = git_state["approved_remote"]
        policy_state = git_state["transport_policy"]
        approved_remote = ApprovedGitRemote(
            canonical_fetch_url=remote_state["canonical_fetch_url"],
            canonical_push_url=remote_state["canonical_push_url"],
            provider_type=remote_state["provider_type"],
            stable_repository_id=remote_state.get("stable_repository_id"),
            required_owner_org=remote_state["required_owner_org"],
            required_visibility_for_push=Visibility(remote_state["required_visibility_for_push"]),
            allowed_refs=tuple(remote_state["allowed_refs"]),
            require_stable_repository_id=bool(remote_state.get("require_stable_repository_id", True)),
        )
        transport_policy = GitTransportPolicy(
            protocol_allowlist=tuple(policy_state["protocol_allowlist"]),
            transport_executable_identity=policy_state["transport_executable_identity"],
            proxy=policy_state.get("proxy"),
            ssh_command=policy_state.get("ssh_command"),
            credential_helper=policy_state.get("credential_helper"),
            ssh_peer_policy=policy_state["ssh_peer_policy"],
            tls_peer_policy=policy_state["tls_peer_policy"],
            effective_transport_config_digest=policy_state["effective_transport_config_digest"],
        )
        remote_view = observed["remote"]
        transport_view = observed["transport"]
        observed_remote = ObservedRepositoryIdentity(
            provider_type=remote_view["provider_type"],
            stable_repository_id=remote_view.get("stable_repository_id"),
            owner_org=remote_view.get("owner_org"),
            visibility=Visibility(remote_view["visibility"]) if remote_view.get("visibility") else None,
            effective_fetch_url=remote_view["effective_fetch_url"],
            effective_push_url=remote_view["effective_push_url"],
        )
        observed_transport = ObservedTransport(
            protocol=transport_view["protocol"],
            transport_executable_identity=transport_view.get("transport_executable_identity"),
            proxy=transport_view.get("proxy"),
            ssh_command=transport_view.get("ssh_command"),
            credential_helper=transport_view.get("credential_helper"),
            effective_transport_config_digest=transport_view.get("effective_transport_config_digest"),
        )
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print(f"sync: REFUSED {error}")
        return 2

    request = SyncRequest(
        store_path=args.store,
        domain=args.domain,
        vault_logical_id=args.vault_id,
        checkout_identity=args.checkout_id,
        vault_root=args.vault,
        checkout_root=args.checkout,
        repository=args.repo,
    )
    if args.push:
        outcome = compose_push(
            request,
            approved_remote=approved_remote,
            transport_policy=transport_policy,
            observed_remote=observed_remote,
            observed_transport=observed_transport,
            source_oid=args.source_oid,
            expected_remote_base_oid=args.expected_base_oid,
            target_ref=args.target_ref,
            exact_refspec=args.refspec,
            expected_git_identity=args.git_identity,
        )
    else:
        outcome = compose_fetch(
            request,
            approved_remote=approved_remote,
            transport_policy=transport_policy,
            observed_remote=observed_remote,
            observed_transport=observed_transport,
            requested_refs=tuple(args.refs),
            verified_at=args.verified_at,
        )
    print(f"sync: {outcome.decision} {outcome.code}")
    return 0 if outcome.decision == "ALLOW" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ainative.multivault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    query = subparsers.add_parser("audit-query", help="print audit records as JSON lines")
    query.add_argument("log", type=Path)
    query.add_argument("--domain")
    query.add_argument("--decision")
    query.add_argument("--reason-code")

    bind = subparsers.add_parser("bind", help="record an operator binding from real measurements")
    bind.add_argument("--store", type=Path, required=True)
    bind.add_argument("--domain", required=True)
    bind.add_argument("--vault-id", required=True)
    bind.add_argument("--checkout-id", required=True)
    bind.add_argument("--vault", type=Path, required=True)
    bind.add_argument("--checkout", type=Path, required=True)
    bind.add_argument("--classification", default="PERSONAL")
    bind.add_argument("--roots", nargs="*", default=[])

    doctor = subparsers.add_parser("doctor", help="fail-closed readiness checks")
    doctor.add_argument("--store", type=Path, required=True)
    doctor.add_argument("--domain", required=True)
    doctor.add_argument("--repo", type=Path, default=Path("."))
    doctor.add_argument("--vault-root", type=Path, default=None)

    context = subparsers.add_parser("context", help="describe the resolved security context")
    context.add_argument("--store", type=Path, required=True)
    context.add_argument("--domain", required=True)
    context.add_argument("--harness", default="UNKNOWN")
    context.add_argument("--provider-class", default="UNKNOWN")
    context.add_argument("--model", default="UNKNOWN")
    context.add_argument("--routing", default="UNKNOWN")

    exec_parser = subparsers.add_parser("exec", help="governed sensitive launch via the exec composition root")
    exec_parser.add_argument("--store", type=Path, required=True)
    exec_parser.add_argument("--domain", required=True)
    exec_parser.add_argument("--vault-id", required=True)
    exec_parser.add_argument("--checkout-id", required=True)
    exec_parser.add_argument("--vault", type=Path, required=True)
    exec_parser.add_argument("--checkout", type=Path, required=True)
    exec_parser.add_argument("--workspace", type=Path, default=None)
    exec_parser.add_argument("--operator-state", type=Path, required=True)
    exec_parser.add_argument("--probe-evidence", type=Path, required=True)
    exec_parser.add_argument("--env", action="append", default=[])
    exec_parser.add_argument("--os-env", action="append", default=[])
    exec_parser.add_argument("argv", nargs=argparse.REMAINDER, help="approved command; place it after all options")

    sync_parser = subparsers.add_parser("sync", help="governed fetch/push through the transfer engine only")
    sync_parser.add_argument("--store", type=Path, required=True)
    sync_parser.add_argument("--domain", required=True)
    sync_parser.add_argument("--vault-id", required=True)
    sync_parser.add_argument("--checkout-id", required=True)
    sync_parser.add_argument("--vault", type=Path, required=True)
    sync_parser.add_argument("--checkout", type=Path, required=True)
    sync_parser.add_argument("--repo", type=Path, required=True)
    sync_parser.add_argument("--git-state", type=Path, required=True)
    sync_parser.add_argument("--observed", type=Path, required=True)
    sync_parser.add_argument("--push", action="store_true")
    sync_parser.add_argument("--refs", nargs="*", default=[])
    sync_parser.add_argument("--verified-at", default="")
    sync_parser.add_argument("--source-oid", default="")
    sync_parser.add_argument("--expected-base-oid", default="")
    sync_parser.add_argument("--target-ref", default="")
    sync_parser.add_argument("--refspec", default="")
    sync_parser.add_argument("--git-identity", default="")

    args = parser.parse_args(argv)

    if args.command == "exec":
        return _exec_command(args)

    if args.command == "sync":
        return _sync_command(args)

    if args.command == "audit-query":
        for record in AuditLog(args.log).query(
            security_domain_id=args.domain,
            decision=args.decision,
            reason_code=args.reason_code,
        ):
            print(json.dumps(asdict(record), sort_keys=True))
        return 0

    if args.command == "bind":
        return _bind(args)

    if args.command == "doctor":
        report = doctor_report(_doctor_checks(args.store, args.domain, args.repo, args.vault_root))
        for name, verdict in report:
            print(f"{verdict}\t{name}")
        return 0 if all(verdict == "PASS" for _name, verdict in report) else 1

    if args.command == "context":
        report = _context_report(args.store, args.domain, args.harness, args.provider_class, args.model, args.routing)
        if report is None:
            print("binding: MISSING")
            return 1
        print(report.render())
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())