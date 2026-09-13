from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from app.schemas import (
    IsolationPolicyRead,
    IsolationPolicyRegistryRead,
    IsolationPreflightCreate,
    IsolationPreflightRead,
)
from app.validators import DomainValidationError

ISOLATION_POLICY_REGISTRY_VERSION = "workload-isolation-registry-v1"
ISOLATION_PREFLIGHT_VERSION = "workload-isolation-preflight-v1"


@dataclass(frozen=True)
class IsolationPolicy:
    policy_id: str
    display_name: str
    workload_kinds: tuple[str, ...]
    network_mode: str
    allowed_network_hosts: tuple[str, ...]
    credential_mode: str
    allowed_secret_envs: tuple[str, ...]
    filesystem_mode: str
    read_only_paths: tuple[str, ...]
    writable_paths: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    subprocess_allowed: bool
    max_execution_seconds: int
    max_output_bytes: int
    policy_version: str = ISOLATION_POLICY_REGISTRY_VERSION

    def to_read(self) -> IsolationPolicyRead:
        return IsolationPolicyRead(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            display_name=self.display_name,
            workload_kinds=list(self.workload_kinds),
            network_mode=self.network_mode,
            allowed_network_hosts=list(self.allowed_network_hosts),
            credential_mode=self.credential_mode,
            allowed_secret_envs=list(self.allowed_secret_envs),
            filesystem_mode=self.filesystem_mode,
            read_only_paths=list(self.read_only_paths),
            writable_paths=list(self.writable_paths),
            allowed_tools=list(self.allowed_tools),
            subprocess_allowed=self.subprocess_allowed,
            max_execution_seconds=self.max_execution_seconds,
            max_output_bytes=self.max_output_bytes,
        )


_LOCAL_TOOLS = (
    "create_ticket",
    "lookup_customer",
    "lookup_internal_document",
    "lookup_policy",
    "search_incidents",
    "summarize_thread",
)

ISOLATION_POLICIES = {
    policy.policy_id: policy
    for policy in (
        IsolationPolicy(
            policy_id="tool-offline-strict",
            display_name="Offline bounded tool evaluation",
            workload_kinds=("tool",),
            network_mode="none",
            allowed_network_hosts=(),
            credential_mode="none",
            allowed_secret_envs=(),
            filesystem_mode="ephemeral",
            read_only_paths=("/app",),
            writable_paths=("/tmp/model-atlas",),
            allowed_tools=_LOCAL_TOOLS,
            subprocess_allowed=False,
            max_execution_seconds=120,
            max_output_bytes=1_048_576,
        ),
        IsolationPolicy(
            policy_id="rag-readonly-internal",
            display_name="Read-only RAG with internal model runtime",
            workload_kinds=("rag",),
            network_mode="internal_allowlist",
            allowed_network_hosts=("ollama", "vllm"),
            credential_mode="none",
            allowed_secret_envs=(),
            filesystem_mode="read_only",
            read_only_paths=("/app", "/data/rag"),
            writable_paths=("/tmp/model-atlas",),
            allowed_tools=(),
            subprocess_allowed=False,
            max_execution_seconds=300,
            max_output_bytes=2_097_152,
        ),
        IsolationPolicy(
            policy_id="tool-rag-internal-authenticated",
            display_name="Tool and RAG evaluation with internal authenticated runtime",
            workload_kinds=("tool", "rag"),
            network_mode="internal_allowlist",
            allowed_network_hosts=("ollama", "vllm"),
            credential_mode="environment_allowlist",
            allowed_secret_envs=("OPENAI_COMPATIBLE_API_KEY",),
            filesystem_mode="read_only",
            read_only_paths=("/app", "/data/rag"),
            writable_paths=("/tmp/model-atlas",),
            allowed_tools=_LOCAL_TOOLS,
            subprocess_allowed=False,
            max_execution_seconds=300,
            max_output_bytes=2_097_152,
        ),
    )
}


def isolation_policy_registry() -> IsolationPolicyRegistryRead:
    policies = [
        policy.to_read()
        for policy in sorted(ISOLATION_POLICIES.values(), key=lambda item: item.policy_id)
    ]
    return IsolationPolicyRegistryRead(
        registry_version=ISOLATION_POLICY_REGISTRY_VERSION,
        policy_count=len(policies),
        policies=policies,
    )


def validate_isolation_preflight(
    request: IsolationPreflightCreate,
) -> IsolationPreflightRead:
    policy = ISOLATION_POLICIES.get(request.policy_id)
    if policy is None:
        raise DomainValidationError("isolation policy was not found")
    violations: list[str] = []
    if request.workload_kind not in policy.workload_kinds:
        violations.append(
            f"workload kind {request.workload_kind} is not allowed by {policy.policy_id}"
        )
    disallowed_tools = sorted(set(request.requested_tools) - set(policy.allowed_tools))
    if disallowed_tools:
        violations.append(f"tools are not allowed: {', '.join(disallowed_tools)}")
    requested_hosts = {_normalized_host(host) for host in request.network_hosts}
    if policy.network_mode == "none" and requested_hosts:
        violations.append("network access is disabled by the isolation policy")
    else:
        disallowed_hosts = sorted(
            requested_hosts - set(policy.allowed_network_hosts)
        )
        if disallowed_hosts:
            violations.append(
                f"network hosts are not allowed: {', '.join(disallowed_hosts)}"
            )
    requested_secrets = set(request.secret_envs)
    if policy.credential_mode == "none" and requested_secrets:
        violations.append("credentials are disabled by the isolation policy")
    else:
        disallowed_secrets = sorted(
            requested_secrets - set(policy.allowed_secret_envs)
        )
        if disallowed_secrets:
            violations.append(
                f"secret environment references are not allowed: {', '.join(disallowed_secrets)}"
            )
    for path in request.read_paths:
        normalized_path = _normalized_path(path)
        if not _within_roots(
            normalized_path,
            (*policy.read_only_paths, *policy.writable_paths),
        ):
            violations.append(f"read path is outside allowed roots: {normalized_path}")
    for path in request.write_paths:
        normalized_path = _normalized_path(path)
        if not _within_roots(normalized_path, policy.writable_paths):
            violations.append(f"write path is outside writable roots: {normalized_path}")
    if request.subprocess_requested and not policy.subprocess_allowed:
        violations.append("subprocess execution is disabled by the isolation policy")
    return IsolationPreflightRead(
        schema_version=ISOLATION_PREFLIGHT_VERSION,
        allowed=not violations,
        policy=policy.to_read(),
        violations=violations,
        normalized_request=request,
    )


def assert_isolation_preflight(request: IsolationPreflightCreate) -> IsolationPreflightRead:
    preflight = validate_isolation_preflight(request)
    if not preflight.allowed:
        raise DomainValidationError(
            "isolation preflight denied: " + "; ".join(preflight.violations)
        )
    return preflight


def execution_isolation_preflights(
    *,
    policy_id: str,
    has_tool_cases: bool,
    has_rag_cases: bool,
    requested_tools: list[str],
    runtime_config: dict[str, Any],
) -> list[IsolationPreflightRead]:
    base_url = runtime_config.get("base_url")
    network_hosts = [str(base_url)] if base_url else []
    secret_envs = [
        str(value)
        for key, value in runtime_config.items()
        if str(key).endswith("_env") and value
    ]
    shared = {
        "policy_id": policy_id,
        "network_hosts": network_hosts,
        "secret_envs": secret_envs,
        "read_paths": list(runtime_config.get("isolation_read_paths") or []),
        "write_paths": list(runtime_config.get("isolation_write_paths") or []),
        "subprocess_requested": bool(runtime_config.get("subprocess_requested")),
    }
    preflights: list[IsolationPreflightRead] = []
    if has_tool_cases:
        preflights.append(
            assert_isolation_preflight(
                IsolationPreflightCreate(
                    **shared,
                    workload_kind="tool",
                    requested_tools=requested_tools,
                )
            )
        )
    if has_rag_cases:
        preflights.append(
            assert_isolation_preflight(
                IsolationPreflightCreate(
                    **shared,
                    workload_kind="rag",
                )
            )
        )
    return preflights


def expected_tools_from_cases(cases: list[Any]) -> list[str]:
    tools: set[str] = set()
    for evaluation_case in cases:
        _collect_tool_names(evaluation_case.expected_tool_schema_json, tools)
    return sorted(tools)


def _collect_tool_names(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"tool_name", "expected_tool"} and isinstance(item, str):
                output.add(item)
            else:
                _collect_tool_names(item, output)
    elif isinstance(value, list):
        for item in value:
            _collect_tool_names(item, output)


def _normalized_host(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"internal://{value}")
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise DomainValidationError("isolation network host is invalid")
    return hostname


def _normalized_path(value: str) -> str:
    if "\x00" in value or not value.startswith("/"):
        raise DomainValidationError("isolation filesystem paths must be absolute POSIX paths")
    parts = PurePosixPath(value).parts
    if ".." in parts:
        raise DomainValidationError("isolation filesystem paths cannot contain parent traversal")
    return posixpath.normpath(value)


def _within_roots(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots)
