from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RecommendationScenario
from app.schemas import (
    RecommendationScenarioCreate,
    RecommendationScenarioRead,
    RecommendationScenarioUpdate,
)
from app.schemas.recommendations import RecommendationRequest
from app.validators import DomainValidationError


def _read_model(entity: RecommendationScenario) -> RecommendationScenarioRead:
    return RecommendationScenarioRead(
        id=entity.id,
        name=entity.name,
        description=entity.description,
        request=RecommendationRequest.model_validate(entity.request_json),
        created_at=entity.created_at.isoformat(),
        updated_at=entity.updated_at.isoformat(),
    )


def _get_entity(db: Session, scenario_id: UUID) -> RecommendationScenario:
    entity = db.get(RecommendationScenario, scenario_id)
    if entity is None:
        raise DomainValidationError("recommendation scenario was not found")
    return entity


def list_scenarios(
    db: Session,
    *,
    limit: int,
    offset: int,
) -> list[RecommendationScenarioRead]:
    statement = (
        select(RecommendationScenario)
        .order_by(RecommendationScenario.updated_at.desc(), RecommendationScenario.name)
        .offset(offset)
        .limit(limit)
    )
    return [_read_model(entity) for entity in db.scalars(statement).all()]


def create_scenario(
    db: Session,
    payload: RecommendationScenarioCreate,
) -> RecommendationScenarioRead:
    entity = RecommendationScenario(
        name=payload.name,
        description=payload.description,
        request_json=payload.request.model_dump(mode="json"),
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return _read_model(entity)


def get_scenario(db: Session, scenario_id: UUID) -> RecommendationScenarioRead:
    return _read_model(_get_entity(db, scenario_id))


def update_scenario(
    db: Session,
    scenario_id: UUID,
    payload: RecommendationScenarioUpdate,
) -> RecommendationScenarioRead:
    entity = _get_entity(db, scenario_id)
    if "name" in payload.model_fields_set:
        entity.name = payload.name or entity.name
    if "description" in payload.model_fields_set:
        entity.description = payload.description
    if "request" in payload.model_fields_set and payload.request is not None:
        entity.request_json = payload.request.model_dump(mode="json")
    db.commit()
    db.refresh(entity)
    return _read_model(entity)


def delete_scenario(db: Session, scenario_id: UUID) -> None:
    entity = _get_entity(db, scenario_id)
    db.delete(entity)
    db.commit()
