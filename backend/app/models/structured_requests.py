from __future__ import annotations

from app.models.base import (
    GUID,
    JSON,
    Base,
    CheckConstraint,
    ForeignKey,
    Integer,
    Mapped,
    String,
    Text,
    TimestampMixin,
    UTCDateTime,
    dt,
    mapped_column,
    utcnow,
    uuid,
)


class StructuredRequest(TimestampMixin, Base):
    __tablename__ = "structured_requests"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    draft_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_json: Mapped[dict | None] = mapped_column(JSON)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    executed_check_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    events_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    __mapper_args__ = {"version_id_col": lock_version}
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_structured_request_revision"),
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'revoked')", name="ck_structured_request_status"
        ),
    )


class StructuredRequestCheck(Base):
    __tablename__ = "structured_request_checks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("structured_requests.id"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    generation_json: Mapped[dict | None] = mapped_column(JSON)
    verdict_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    execution_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
