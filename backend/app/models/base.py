from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, TypeDecorator


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def normalize_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


class GUID(TypeDecorator[uuid.UUID]):
    """Portable UUID type that uses native UUIDs on PostgreSQL."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> uuid.UUID | str | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | None:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class UTCDateTime(TypeDecorator[dt.datetime]):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: Any, dialect: Any) -> dt.datetime | None:
        if value is None:
            return None
        return normalize_utc(value)

    def process_result_value(self, value: Any, dialect: Any) -> dt.datetime | None:
        return normalize_utc(value)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


def _normalize_timestamps(_: Any, __: Any, target: Any) -> None:
    for field in ("created_at", "updated_at", "started_at", "completed_at"):
        if hasattr(target, field):
            setattr(target, field, normalize_utc(getattr(target, field)))


def register_timestamp_listeners(*mapped_classes: type[Any]) -> None:
    for mapped_class in mapped_classes:
        event.listen(mapped_class, "before_insert", _normalize_timestamps)
        event.listen(mapped_class, "before_update", _normalize_timestamps)


__all__ = [
    "Any",
    "Base",
    "Boolean",
    "CheckConstraint",
    "Float",
    "ForeignKey",
    "GUID",
    "Integer",
    "JSON",
    "Mapped",
    "String",
    "Text",
    "TimestampMixin",
    "UTCDateTime",
    "UniqueConstraint",
    "dt",
    "mapped_column",
    "register_timestamp_listeners",
    "relationship",
    "utcnow",
    "uuid",
]
