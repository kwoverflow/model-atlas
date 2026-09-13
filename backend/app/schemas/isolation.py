from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

IsolationWorkloadKind = Literal["tool", "rag"]
IsolationNetworkMode = Literal["none", "internal_allowlist"]
IsolationCredentialMode = Literal["none", "environment_allowlist"]
IsolationFilesystemMode = Literal["ephemeral", "read_only"]


class IsolationPolicyRead(BaseModel):
    policy_id: str
    policy_version: str
    display_name: str
    workload_kinds: list[IsolationWorkloadKind]
    network_mode: IsolationNetworkMode
    allowed_network_hosts: list[str]
    credential_mode: IsolationCredentialMode
    allowed_secret_envs: list[str]
    filesystem_mode: IsolationFilesystemMode
    read_only_paths: list[str]
    writable_paths: list[str]
    allowed_tools: list[str]
    subprocess_allowed: bool
    max_execution_seconds: int
    max_output_bytes: int


class IsolationPolicyRegistryRead(BaseModel):
    registry_version: str
    policy_count: int
    policies: list[IsolationPolicyRead]


class IsolationPreflightCreate(BaseModel):
    policy_id: str = Field(min_length=1, max_length=120)
    workload_kind: IsolationWorkloadKind
    requested_tools: list[str] = Field(default_factory=list, max_length=100)
    network_hosts: list[str] = Field(default_factory=list, max_length=50)
    secret_envs: list[str] = Field(default_factory=list, max_length=20)
    read_paths: list[str] = Field(default_factory=list, max_length=100)
    write_paths: list[str] = Field(default_factory=list, max_length=100)
    subprocess_requested: bool = False

    @field_validator(
        "requested_tools",
        "network_hosts",
        "secret_envs",
        "read_paths",
        "write_paths",
    )
    @classmethod
    def validate_bounded_strings(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 500 for value in normalized):
            raise ValueError("isolation request values must contain 1 to 500 characters")
        return list(dict.fromkeys(normalized))


class IsolationPreflightRead(BaseModel):
    schema_version: str
    allowed: bool
    policy: IsolationPolicyRead
    violations: list[str]
    normalized_request: IsolationPreflightCreate
