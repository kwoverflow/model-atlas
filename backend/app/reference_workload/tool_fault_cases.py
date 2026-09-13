"""Separate public requests from evaluator-only labels for the fault baseline."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.benchmark_execution import _available_tool_descriptors
from app.services.tool_call_contract import compile_bounded_tool_call
from app.services.tool_execution import ToolRegistry


class FaultBaselineCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^TFB-[0-9]{3}$")
    request: str = Field(min_length=1)
    expected_tool: str = Field(min_length=1)
    expected_arguments: dict[str, str]


class FaultBaselinePack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["tool-fault-baseline-cases-v1"]
    authority: Literal["local_authored_diagnostic"]
    human_reviewed: Literal[False]
    gate_evidence: Literal[False]
    corpus_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[FaultBaselineCase, ...] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("baseline case IDs must be unique")
        return self


def prepare_baseline_cases(item: FaultBaselineCase, registry: ToolRegistry, context: dict):
    common = {
        "external_case_id": item.id,
        "category": "tool_single_step",
        "title": "Local Tool request",
        "reference_context_json": None,
        "expected_output_json": None,
    }
    # An empty contract enables the adapter's Tool path without supplying any answer labels.
    public = SimpleNamespace(**common, expected_tool_schema_json={}, input_payload_json={})
    public.input_payload_json = {
        "query": item.request,
        "instruction": "Use only the registered local tools. Preserve explicitly requested values.",
        "available_tools": _available_tool_descriptors(public, registry),
        "available_document_ids": list(context["document_ids"]),
        "document_catalog_provenance": {k: v for k, v in context.items() if k != "document_ids"},
    }
    evaluator = SimpleNamespace(
        **common,
        input_payload_json={},
        expected_tool_schema_json={"tool_name": item.expected_tool},
    )
    return public, evaluator


def load_baseline_pack(path: Path, registry: ToolRegistry, context: dict) -> FaultBaselinePack:
    pack = FaultBaselinePack.model_validate_json(path.read_text(encoding="utf-8"))
    if pack.corpus_hash != context["corpus_hash"]:
        raise ValueError("baseline case pack corpus hash does not match the manifest corpus")
    if {case.expected_tool for case in pack.cases} != set(registry.tools):
        raise ValueError("baseline must cover exactly the registered Tool catalog")
    for item in pack.cases:
        public, _ = prepare_baseline_cases(item, registry, context)
        expected = compile_bounded_tool_call(
            json.dumps({"tool_name": item.expected_tool, "arguments": item.expected_arguments}),
            input_payload=public.input_payload_json,
            document_context=context,
        )
        if not expected.execution_allowed:
            raise ValueError(f"invalid expected argument contract for {item.id}")
        if any(value not in item.request for value in item.expected_arguments.values()):
            raise ValueError(f"exact-value baseline requires public argument literals: {item.id}")
    return pack
