from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import configure_mappers

import app.models as models
import app.models.entities as compatibility
from app.db.base import Base as DatabaseBase

EXPECTED_METADATA_HASH = "fba1f807c636ea5c4178db7b391a2300dbd6743118d5c989e23592d23a115c6a"
LAB_TABLES = {
    "structured_requests",
    "structured_request_checks",
    "request_scenario_runs",
    "request_study_attempts",
    "request_workflow_attempts",
}


def test_public_model_imports_and_compatibility_module_resolve_same_classes() -> None:
    assert models.Base is DatabaseBase
    for name in models.__all__:
        assert getattr(models, name) is getattr(compatibility, name)
    assert models.Model.__module__ == "app.models.catalog"
    assert models.BenchmarkRun.__module__ == "app.models.evaluation"
    assert models.AgentExecutionJob.__module__ == "app.models.agent"
    assert models.OperationalMetricSnapshot.__module__ == "app.models.operations"
    assert models.OIDCBrowserSession.__module__ == "app.models.identity"
    assert models.EvidenceTrustRoot.__module__ == "app.models.trust"
    assert models.ReleaseDecision.__module__ == "app.models.release"


def test_split_model_metadata_matches_pre_split_contract() -> None:
    configure_mappers()

    assert LAB_TABLES <= models.Base.metadata.tables.keys()
    assert len(models.Base.metadata.tables) == 47 + len(LAB_TABLES)
    assert _metadata_hash() == EXPECTED_METADATA_HASH


def _metadata_hash() -> str:
    tables: list[dict[str, Any]] = []
    for name, table in sorted(models.Base.metadata.tables.items()):
        # Keep the original 47-table contract pinned; the new lab is additive.
        if name in LAB_TABLES:
            continue
        tables.append(
            {
                "table": name,
                "columns": [
                    {
                        "name": column.name,
                        "type": str(column.type),
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "unique": column.unique,
                        "index": column.index,
                        "foreign_keys": sorted(
                            (foreign_key.target_fullname, foreign_key.ondelete)
                            for foreign_key in column.foreign_keys
                        ),
                    }
                    for column in table.columns
                ],
                "constraints": sorted(
                    (
                        type(constraint).__name__,
                        constraint.name or "",
                        tuple(sorted(column.name for column in getattr(constraint, "columns", []))),
                    )
                    for constraint in table.constraints
                ),
                "indexes": sorted(
                    (
                        index.name or "",
                        index.unique,
                        tuple(column.name for column in index.columns),
                    )
                    for index in table.indexes
                ),
            }
        )
    payload = json.dumps(tables, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
