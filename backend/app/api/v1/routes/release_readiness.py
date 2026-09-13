from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import ReleaseReadinessSnapshot
from app.services.release_readiness import (
    build_release_readiness_snapshot,
    render_release_readiness_markdown,
)

router = APIRouter()


@router.get("/snapshot", response_model=ReleaseReadinessSnapshot)
def get_snapshot(
    gate_evaluation_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ReleaseReadinessSnapshot:
    return build_release_readiness_snapshot(db, gate_evaluation_id=gate_evaluation_id)


@router.get("/snapshot.md")
def get_snapshot_markdown(
    gate_evaluation_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> Response:
    snapshot = build_release_readiness_snapshot(db, gate_evaluation_id=gate_evaluation_id)
    return Response(
        content=render_release_readiness_markdown(snapshot),
        media_type="text/markdown; charset=utf-8",
    )
