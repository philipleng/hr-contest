"""005 · 候选人来源表

与 database/migrations/005_candidate_source.sql 等价。
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0003"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("candidate_source"):
        op.execute(
            """
            CREATE TABLE candidate_source (
              id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              applicant_id        BIGINT UNSIGNED NOT NULL,
              platform            VARCHAR(50)     NOT NULL
                                  COMMENT 'jobstreet/facebook/walkin/referral/staff/import/other',
              platform_profile_id VARCHAR(191)    NULL COMMENT '平台侧唯一标识，可为空',
              source_url          VARCHAR(500)    NULL,
              raw_payload         MEDIUMTEXT      NULL COMMENT '原始片段，应用层截断至 512KB',
              payload_truncated   TINYINT         NOT NULL DEFAULT 0,
              first_seen_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              last_seen_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              UNIQUE KEY uk_platform_profile (platform, platform_profile_id),
              KEY idx_applicant (applicant_id),
              KEY idx_platform (platform)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              ROW_FORMAT=DYNAMIC COMMENT='候选人来源'
            """
        )
    op.execute(
        "INSERT IGNORE INTO schema_version (version, name) "
        "VALUES (5, '005_candidate_source.sql')"
    )


def downgrade() -> None:
    if _has_table("candidate_source"):
        op.execute("DROP TABLE candidate_source")
