from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import HardwareProfile, Model, ModelArtifact
from app.repositories import BaseRepository
from app.schemas import HardwareProfileCreate, ModelArtifactCreate, ModelCreate
from app.validators import DomainValidationError

hardware_profiles = BaseRepository(HardwareProfile)
models = BaseRepository(Model)
model_artifacts = BaseRepository(ModelArtifact)


def list_hardware_profiles(db: Session, limit: int, offset: int) -> Sequence[HardwareProfile]:
    return hardware_profiles.list(db, limit=limit, offset=offset)


def create_hardware_profile(db: Session, payload: HardwareProfileCreate) -> HardwareProfile:
    return hardware_profiles.create(db, payload.model_dump())


def list_models(db: Session, limit: int, offset: int) -> Sequence[Model]:
    return models.list(db, limit=limit, offset=offset)


def create_model(db: Session, payload: ModelCreate) -> Model:
    return models.create(db, payload.model_dump())


def list_model_artifacts(db: Session, limit: int, offset: int) -> Sequence[ModelArtifact]:
    return model_artifacts.list(db, limit=limit, offset=offset)


def create_model_artifact(db: Session, payload: ModelArtifactCreate) -> ModelArtifact:
    if models.get(db, payload.model_id) is None:
        raise DomainValidationError("model_artifact must reference an existing model")
    return model_artifacts.create(db, payload.model_dump())


def get_model_artifact(db: Session, artifact_id: UUID) -> ModelArtifact | None:
    return model_artifacts.get(db, artifact_id)
