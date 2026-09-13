from app.models.base import (
    GUID,
    JSON,
    Base,
    ForeignKey,
    Integer,
    Mapped,
    String,
    UTCDateTime,
    dt,
    mapped_column,
    utcnow,
    uuid,
)


class RequestWorkflowAttempt(Base):
    __tablename__ = "request_workflow_attempts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("structured_requests.id"), unique=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    help_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    help_events_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    submission_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    __mapper_args__ = {"version_id_col": lock_version}
