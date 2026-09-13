from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    ReleaseDecisionActionCreate,
    ReleaseDecisionActionRead,
    ReleaseDecisionCreate,
    ReleaseDecisionRead,
    ReleaseSnapshotDiffRead,
)
from app.services.operator_identity import local_operator_identity
from app.services.release_decisions import (
    build_release_decision_snapshot_diff,
    create_release_decision,
    create_release_decision_action,
    get_release_decision,
    list_release_decision_actions,
    list_release_decisions,
    release_decision_read,
    render_release_decision_markdown,
)

router = APIRouter()


@router.post("", response_model=ReleaseDecisionRead, status_code=201)
def create_decision(
    payload: ReleaseDecisionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ReleaseDecisionRead:
    release_decision = create_release_decision(
        db,
        payload,
        trusted_operator_identity=getattr(request.state, "operator_identity", None),
    )
    return release_decision_read(db, release_decision)


@router.get("", response_model=list[ReleaseDecisionRead])
def list_decisions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    gate_evaluation_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[ReleaseDecisionRead]:
    return [
        release_decision_read(db, decision)
        for decision in list_release_decisions(
            db,
            limit=limit,
            offset=offset,
            gate_evaluation_id=gate_evaluation_id,
        )
    ]


@router.get("/{release_decision_id}", response_model=ReleaseDecisionRead)
def get_decision(
    release_decision_id: UUID,
    db: Session = Depends(get_db),
) -> ReleaseDecisionRead:
    return release_decision_read(
        db,
        get_release_decision(db, release_decision_id),
    )


@router.get(
    "/{release_decision_id}/actions",
    response_model=list[ReleaseDecisionActionRead],
)
def list_decision_actions(
    release_decision_id: UUID,
    db: Session = Depends(get_db),
) -> list[ReleaseDecisionActionRead]:
    get_release_decision(db, release_decision_id)
    return list_release_decision_actions(
        db,
        release_decision_id=release_decision_id,
    )


@router.post(
    "/{release_decision_id}/actions",
    response_model=ReleaseDecisionActionRead,
    status_code=201,
)
def create_decision_action(
    release_decision_id: UUID,
    payload: ReleaseDecisionActionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ReleaseDecisionActionRead:
    identity = (
        getattr(request.state, "operator_identity", None)
        or local_operator_identity()
    )
    return create_release_decision_action(
        db,
        release_decision_id=release_decision_id,
        payload=payload,
        signer_identity=identity,
    )


@router.get("/{release_decision_id}/snapshot.json")
def export_release_decision_snapshot_json(
    release_decision_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    release_decision = get_release_decision(db, release_decision_id)
    return Response(
        content=json.dumps(
            release_decision.snapshot_json,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="model-atlas-release-snapshot.json"'
        },
    )


@router.get("/{release_decision_id}/snapshot-diff", response_model=ReleaseSnapshotDiffRead)
def get_release_decision_snapshot_diff(
    release_decision_id: UUID,
    db: Session = Depends(get_db),
) -> ReleaseSnapshotDiffRead:
    return build_release_decision_snapshot_diff(db, release_decision_id)


@router.get("/{release_decision_id}/report.md")
def export_release_decision_markdown(
    release_decision_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    release_decision = get_release_decision(db, release_decision_id)
    return Response(
        content=render_release_decision_markdown(release_decision),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="model-atlas-release-decision.md"'
        },
    )
