from app.models.base import (
    GUID,
    JSON,
    Base,
    Integer,
    Mapped,
    String,
    UTCDateTime,
    dt,
    mapped_column,
    utcnow,
    uuid,
)


class RequestScenarioRun(Base):
    __tablename__ = "request_scenario_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class RequestStudyAttempt(Base):
    __tablename__ = "request_study_attempts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer_json: Mapped[dict | None] = mapped_column(JSON)
    answer_hash: Mapped[str | None] = mapped_column(String(64))
    result_json: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    __mapper_args__ = {"version_id_col": lock_version}
