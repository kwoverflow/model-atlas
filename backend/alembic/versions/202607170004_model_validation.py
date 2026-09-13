"""Add durable local model validation campaign jobs.

Revision ID: 202607170004
Revises: 202607170003
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202607170004"
down_revision: str | None = "202607170003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
        "'traffic_evidence_import', 'model_validation_campaign')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
        "'traffic_evidence_import')",
    )
