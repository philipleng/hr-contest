"""003 · applicant 增量列与索引

与 database/migrations/003_applicant_patch.sql 等价：
- 5 个新列按 information_schema 判断后添加
- updated_at 三步走，已有正确定义时不重刷历史值
- 2 个索引判断后创建
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}


def _updated_at_ok(bind) -> bool:
    count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'applicant'
              AND COLUMN_NAME = 'updated_at'
              AND IS_NULLABLE = 'NO'
              AND COLUMN_DEFAULT = 'CURRENT_TIMESTAMP'
              AND EXTRA LIKE '%on update CURRENT_TIMESTAMP%'
            """
        )
    ).scalar()
    return count == 1


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, "applicant")

    if "phone_normalized" not in cols:
        op.execute(
            "ALTER TABLE applicant ADD COLUMN phone_normalized VARCHAR(20) NULL "
            "COMMENT '归一化手机号，仅检索与去重提示' AFTER phone_alt"
        )
    if "availability" not in cols:
        op.execute(
            "ALTER TABLE applicant ADD COLUMN availability TINYINT NOT NULL DEFAULT 0 "
            "COMMENT '0未知 1在找工作 2在职 3暂不考虑' AFTER available_time"
        )
    if "available_from" not in cols:
        op.execute(
            "ALTER TABLE applicant ADD COLUMN available_from DATE NULL "
            "COMMENT '可到岗日期' AFTER availability"
        )
    if "intent_tags" not in cols:
        op.execute(
            "ALTER TABLE applicant ADD COLUMN intent_tags VARCHAR(255) NULL "
            "COMMENT '岗位意向标签，小写逗号分隔' AFTER preferred_location"
        )
    if "merged_into_id" not in cols:
        op.execute(
            "ALTER TABLE applicant ADD COLUMN merged_into_id BIGINT UNSIGNED NULL "
            "COMMENT '被合并到的主档 ID' AFTER deleted_at"
        )

    if not _updated_at_ok(bind):
        cols = _columns(bind, "applicant")
        if "updated_at" not in cols:
            op.execute(
                "ALTER TABLE applicant ADD COLUMN updated_at DATETIME NULL "
                "COMMENT '最后更新时间'"
            )
        op.execute(
            "UPDATE applicant SET updated_at = created_at WHERE updated_at IS NULL"
        )
        op.execute(
            "ALTER TABLE applicant MODIFY updated_at DATETIME NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )

    indexes = _indexes(bind, "applicant")
    if "idx_phone_normalized" not in indexes:
        op.execute("CREATE INDEX idx_phone_normalized ON applicant (phone_normalized)")
    if "idx_status_created" not in indexes:
        op.execute("CREATE INDEX idx_status_created ON applicant (status, created_at)")

    op.execute(
        "INSERT IGNORE INTO schema_version (version, name) "
        "VALUES (3, '003_applicant_patch.sql')"
    )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = _indexes(bind, "applicant")
    if "idx_status_created" in indexes:
        op.execute("DROP INDEX idx_status_created ON applicant")
    if "idx_phone_normalized" in indexes:
        op.execute("DROP INDEX idx_phone_normalized ON applicant")

    cols = _columns(bind, "applicant")
    for column in ("merged_into_id", "intent_tags", "available_from", "availability",
                   "phone_normalized"):
        if column in cols:
            op.execute(f"ALTER TABLE applicant DROP COLUMN {column}")
    # updated_at 可能迁移前就已存在，降级时不删除
