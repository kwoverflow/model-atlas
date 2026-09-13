from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.services.tool_execution import validate_json_schema

TOOL_CALL_CONTRACT_VERSION = "bounded-tool-call-contract-v2"
_SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "minLength",
    "maxLength",
    "description",
    "title",
}


@dataclass(frozen=True)
class ToolCallCompilation:
    normalized_output: str
    tool_name: str | None
    schema_errors: tuple[str, ...]
    boundary_errors: tuple[str, ...]
    arguments_hash: str | None
    document_reference_status: str
    document_corpus_hash: str | None
    failure_mode: str | None

    @property
    def execution_allowed(self) -> bool:
        return not self.schema_errors and not self.boundary_errors

    def audit_record(self) -> dict[str, Any]:
        return {
            "schema_version": TOOL_CALL_CONTRACT_VERSION,
            "compiler_id": "public_tool_request_compiler",
            "compiler_version": TOOL_CALL_CONTRACT_VERSION,
            "applied": True,
            "tool_name": self.tool_name,
            "changed": False,
            "removed_arguments": [],
            "filled_arguments": [],
            "replaced_arguments": [],
            "raw_arguments_hash": self.arguments_hash,
            "normalized_arguments_hash": self.arguments_hash,
            "schema_valid": not self.schema_errors,
            "schema_errors": list(self.schema_errors),
            "boundary_errors": list(self.boundary_errors),
            "execution_allowed": self.execution_allowed,
            "document_reference_status": self.document_reference_status,
            "document_corpus_hash": self.document_corpus_hash,
            "semantic_validation_scope": "document_id_membership_only",
            "query_semantics": "not_verified",
            "failure_mode": self.failure_mode,
            "failure_mode_source": "explicit_runtime_configuration",
            "source": "public_tool_registry_and_runtime_document_catalog",
            "uses_expected_tool_contract": False,
        }


def compile_bounded_tool_call(
    output: str,
    *,
    input_payload: dict[str, Any],
    document_context: dict[str, Any] | None = None,
    allowed_failure_mode: str | None = None,
) -> ToolCallCompilation:
    """Inspect one call without inventing, deleting, coercing, or truncating arguments."""
    if allowed_failure_mode not in (None, "transient_once", "permanent"):
        raise ValueError("tool_failure_simulation must be transient_once, permanent, or null")
    schema_errors: list[str] = []
    boundary_errors: list[str] = []
    tool_name = None
    arguments_hash = None
    reference_status = "not_applicable"
    corpus_hash = None
    try:
        tool_name, arguments = _single_tool_call(output)
        arguments_hash = hashlib.sha256(_canonical(arguments).encode()).hexdigest()
    except ValueError as exc:
        schema_errors.append(str(exc))
    else:
        # Only the envelope is canonicalized; argument values remain unchanged.
        output = _canonical({"tool_name": tool_name, "arguments": arguments})
        try:
            schema = _selected_schema(input_payload.get("available_tools"), tool_name)
            _check_supported_schema(schema)
        except ValueError as exc:
            schema_errors.append(str(exc))
        else:
            schema_errors.extend(validate_json_schema(arguments, schema))
        if "simulate_failure" in arguments and (
            allowed_failure_mode is None or arguments["simulate_failure"] != allowed_failure_mode
        ):
            boundary_errors.append("failure_simulation_not_authorized")
        if "document_id" in arguments:
            reference_status = "catalog_unavailable"
            if isinstance(document_context, dict):
                ids = document_context.get("document_ids")
                corpus_hash = document_context.get("corpus_hash")
                if (
                    isinstance(ids, list)
                    and all(isinstance(value, str) for value in ids)
                    and isinstance(corpus_hash, str)
                    and corpus_hash
                ):
                    reference_status = (
                        "verified" if arguments["document_id"] in ids else "not_in_catalog"
                    )
            if reference_status != "verified":
                boundary_errors.append(f"document_id_{reference_status}")
    return ToolCallCompilation(
        output,
        tool_name,
        tuple(schema_errors),
        tuple(boundary_errors),
        arguments_hash,
        reference_status,
        corpus_hash,
        allowed_failure_mode,
    )


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number: {value}")


def _read_json(value: str) -> Any:
    return json.loads(value, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _single_tool_call(output: str) -> tuple[str, dict[str, Any]]:
    parsed = _read_json(output)
    if not isinstance(parsed, dict):
        raise ValueError("tool call must be an object")
    shapes = [
        key for key in ("tool_calls", "tool_call", "tool_name", "name", "function") if key in parsed
    ]
    if len(shapes) != 1:
        raise ValueError("tool call envelope is missing or ambiguous")
    if shapes[0] == "tool_calls":
        calls = parsed["tool_calls"]
        if not isinstance(calls, list) or len(calls) != 1:
            raise ValueError("exactly one tool call is required")
        parsed = calls[0]
    elif shapes[0] == "tool_call":
        parsed = parsed["tool_call"]
    if not isinstance(parsed, dict):
        raise ValueError("tool call must be an object")
    if "function" in parsed:
        if "tool_name" in parsed or "name" in parsed:
            raise ValueError("tool call has conflicting names")
        parsed = parsed["function"]
    if not isinstance(parsed, dict) or ("tool_name" in parsed) == ("name" in parsed):
        raise ValueError("tool call must have exactly one name")
    name = parsed.get("tool_name", parsed.get("name"))
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("tool name must be a nonblank identifier without surrounding whitespace")
    arguments = parsed.get("arguments")
    if isinstance(arguments, str):
        arguments = _read_json(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an explicit object")
    return name, arguments


def _selected_schema(descriptors: Any, tool_name: str) -> dict[str, Any]:
    if not isinstance(descriptors, list):
        raise ValueError("public tool descriptors are unavailable")
    names: set[str] = set()
    selected = None
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            raise ValueError("invalid public tool descriptor")
        name = descriptor.get("tool_name")
        if not isinstance(name, str) or not name or name != name.strip() or name in names:
            raise ValueError("invalid or duplicate public tool name")
        names.add(name)
        if name == tool_name:
            selected = descriptor.get("argument_schema")
    if not isinstance(selected, dict) or selected.get("type") != "object":
        raise ValueError("selected tool has no public object argument schema")
    return selected


def _check_supported_schema(schema: dict[str, Any]) -> None:
    if set(schema) - _SCHEMA_KEYS:
        raise ValueError("argument schema contains unsupported constraints")
    if not isinstance(schema.get("type"), str) or schema["type"] not in {
        "object",
        "array",
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    }:
        raise ValueError("argument schema requires a supported explicit type")
    for key in ("minLength", "maxLength"):
        if key in schema and (type(schema[key]) is not int or schema[key] < 0):
            raise ValueError("invalid argument string length constraint")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ValueError("invalid argument enum")
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        raise ValueError("unsupported additionalProperties schema")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if (
        not isinstance(properties, dict)
        or not isinstance(required, list)
        or any(not isinstance(key, str) or key not in properties for key in required)
    ):
        raise ValueError("invalid argument properties or required fields")
    children = list(properties.values())
    if "items" in schema:
        children.append(schema["items"])
    for child in children:
        if not isinstance(child, dict):
            raise ValueError("invalid child argument schema")
        _check_supported_schema(child)
