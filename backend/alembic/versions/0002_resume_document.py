"""002 · 多简历文件表

与 database/migrations/002_resume_document.sql 完全一致，包含 ascii_bin
hash 与 ROW_FORMAT=DYNAMIC。
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("resume_document"):
        op.execute(
            """
            CREATE TABLE resume_document (
              id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              applicant_id  BIGINT UNSIGNED NULL COMMENT '允许为空：文件先入库，人后补',
              oss_key       VARCHAR(255) NOT NULL COMMENT '私有存储相对路径',
              file_name     VARCHAR(255) NOT NULL COMMENT '原始文件名',
              file_ext      VARCHAR(16)  NOT NULL COMMENT '小写扩展名，含点',
              file_size     INT          NOT NULL DEFAULT 0 COMMENT '字节',
              content_hash  CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL
                            COMMENT 'sha256；文件缺失时为 NULL',
              text_excerpt  MEDIUMTEXT   NULL COMMENT '提取正文，供检索与 AI 抽取',
              extract_state TINYINT      NOT NULL DEFAULT 0
                            COMMENT '0待提取 1成功 2失败 3扫描件 4文件缺失',
              source_id     BIGINT UNSIGNED NULL COMMENT '对应 candidate_source.id',
              created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              KEY idx_applicant_created (applicant_id, created_at),
              KEY idx_hash (content_hash),
              KEY idx_extract_state (extract_state)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              ROW_FORMAT=DYNAMIC COMMENT='简历文件'
            """
        )
    op.execute(
        "INSERT IGNORE INTO schema_version (version, name) "
        "VALUES (2, '002_resume_document.sql')"
    )


def downgrade() -> None:
    if _has_table("resume_document"):
        op.execute("DROP TABLE resume_document")
