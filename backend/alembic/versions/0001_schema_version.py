"""001 · 迁移执行日志表

与 database/migrations/001_schema_version.sql 等价，保留 schema_version
便于沿用旧的版本核对方式；Alembic 自身另用 alembic_version 记录。
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = "0000"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("schema_version"):
        op.execute(
            """
            CREATE TABLE schema_version (
              version    INT          NOT NULL COMMENT '迁移序号，与脚本文件名前缀一致',
              name       VARCHAR(100) NOT NULL COMMENT '脚本文件名',
              applied_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (version)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='迁移执行日志'
            """
        )
    op.execute(
        "INSERT IGNORE INTO schema_version (version, name) "
        "VALUES (1, '001_schema_version.sql')"
    )


def downgrade() -> None:
    if _has_table("schema_version"):
        op.execute("DROP TABLE schema_version")
