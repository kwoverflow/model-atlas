from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository[ModelT]:
    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    def get(self, db: Session, entity_id: UUID) -> ModelT | None:
        return db.get(self.model, entity_id)

    def list(
        self,
        db: Session,
        *,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> Sequence[ModelT]:
        statement: Select[Any] = select(self.model)
        if filters:
            for field_name, value in filters.items():
                if value is not None:
                    statement = statement.where(getattr(self.model, field_name) == value)
        statement = statement.offset(offset).limit(limit)
        return db.scalars(statement).all()

    def count(self, db: Session) -> int:
        return int(db.scalar(select(func.count()).select_from(self.model)) or 0)

    def create(self, db: Session, payload: dict[str, Any]) -> ModelT:
        entity = self.model(**payload)
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity
