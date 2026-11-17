"""007 · 联系记录表

与 database/migrations/007_contact_log.sql 等价。
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0005"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("contact_log"):
        op.execute(
            """
            CREATE TABLE contact_log (
              id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              applicant_id   BIGINT UNSIGNED NOT NULL,
              channel        VARCHAR(20)     NOT NULL
                             COMMENT 'phone/sms/whatsapp/messenger/email/inperson',
              result         VARCHAR(30)     NOT NULL
                             COMMENT 'reached/no_answer/wrong_number/refused/interview_booked',
              note           VARCHAR(500)    NULL,
              operator_id    BIGINT UNSIGNED NULL,
              next_follow_at DATETIME        NULL COMMENT '为空表示无需跟进',
              created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              KEY idx_applicant_time (applicant_id, created_at),
              KEY idx_next_follow (next_follow_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='联系记录'
            """
        )
    op.execute(
        "INSERT IGNORE INTO schema_version (version, name) "
        "VALUES (7, '007_contact_log.sql')"
    )


def downgrade() -> None:
    if _has_table("contact_log"):
        op.execute("DROP TABLE contact_log")
