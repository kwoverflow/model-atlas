"""release decision signer identity

Revision ID: 202607090003
Revises: 202607090002
Create Date: 2026-07-09 00:00:02.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607090003"
down_revision: str | None = "202607090002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "release_decisions",
        sa.Column(
            "signer_identity_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column(
        "release_decisions",
        sa.Column(
            "identity_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "release_decisions",
        sa.Column("signature_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "release_decisions",
        sa.Column("signature_statement", sa.Text(), nullable=True),
    )
    op.alter_column("release_decisions", "signer_identity_json", server_default=None)
    op.alter_column("release_decisions", "identity_verified", server_default=None)
    op.create_index(
        op.f("ix_release_decisions_identity_verified"),
        "release_decisions",
        ["identity_verified"],
    )
    op.create_index(
        op.f("ix_release_decisions_signature_hash"),
        "release_decisions",
        ["signature_hash"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_release_decisions_signature_hash"), table_name="release_decisions")
    op.drop_index(op.f("ix_release_decisions_identity_verified"), table_name="release_decisions")
    op.drop_column("release_decisions", "signature_statement")
    op.drop_column("release_decisions", "signature_hash")
    op.drop_column("release_decisions", "identity_verified")
    op.drop_column("release_decisions", "signer_identity_json")
