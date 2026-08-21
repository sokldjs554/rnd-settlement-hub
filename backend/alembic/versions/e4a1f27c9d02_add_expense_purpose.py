"""add expense purpose (사용 용도)

규정(국가연구개발혁신법 시행령 별표 2)이 비목을 품목이 아니라 '용도'로 가르므로,
용도를 입력받아 AI 비목 제안(R-CAT-001)의 판단 근거로 쓴다.

Revision ID: e4a1f27c9d02
Revises: 9cb769e9b138
"""

import sqlalchemy as sa
from alembic import op

revision = "e4a1f27c9d02"
down_revision = "9cb769e9b138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("purpose", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("expenses", "purpose")
