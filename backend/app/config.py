"""全局配置：从 backend/.env 读取环境变量"""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

logger = logging.getLogger(__name__)

_FORBIDDEN_PROD_JWT_SECRETS = frozenset({
    "",
    "dev-secret-change-me",
    "your-jwt-secret-here-change-in-production",
    "REPLACE_WITH_RANDOM_LONG_SECRET",
    "test-only-secret-not-for-production",
})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # 运行环境与文档 / CORS 安全开关
    APP_ENV: str = "development"
    ENABLE_API_DOCS: bool | None = None
    CORS_ORIGINS: str = "*"

    # 真实值请配置在 backend/.env（从 .env.example 复制后填写）
    # 二选一：直接给完整 DATABASE_URL，或分别配置下面的 DB_* 变量。
    DATABASE_URL: str = ""
    # 迁移专用连接串（可选；生产 hr_migrate 账号仅授 DDL 权限，留空则回退主连接串）
    MIGRATE_DATABASE_URL: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "hr_system"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    # 启动时自动执行 Alembic 迁移；生产由部署环境显式打开
    AUTO_MIGRATE: bool = False

    # 业务时区（库表 DATETIME 存无时区墙上时间，统一按业务时区生成与边界比较）
    APP_TIMEZONE: str = "Asia/Manila"

    # 匿名上传配额（已登录 staff 不限；数值可按部署环境覆盖）
    UPLOAD_ANON_DAILY_REQUESTS: int = 50
    UPLOAD_ANON_DAILY_BYTES: int = 500 * 1024 * 1024
    UPLOAD_ANON_PER_MINUTE: int = 10
    UPLOAD_MIN_FREE_DISK_BYTES: int = 5 * 1024 ** 3

    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72

    # 阿里云 OSS（本地开发可留空，将使用本地上传兜底）
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_ROLE_ARN: str = ""
    OSS_BUCKET: str = ""
    OSS_REGION: str = "ap-southeast-6"
    OSS_ENDPOINT: str = ""

    @property
    def is_production(self) -> bool:
        """当前是否运行在生产环境。"""
        return self.APP_ENV.strip().lower() == "production"

    @property
    def api_docs_enabled(self) -> bool:
        """是否开放 Swagger / ReDoc / OpenAPI 文档（生产默认关闭，可用 ENABLE_API_DOCS 显式覆盖）。"""
        if self.ENABLE_API_DOCS is not None:
            return self.ENABLE_API_DOCS
        return not self.is_production

    @property
    def cors_origins_list(self) -> list[str]:
        """解析 CORS_ORIGINS（逗号分隔）；为空时开发态回退 ['*']，生产态返回 []。"""
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        if origins:
            return origins
        return [] if self.is_production else ["*"]

    def validate_runtime_security(self) -> None:
        """生产环境启动安全检查：禁止默认/占位/过短的 JWT_SECRET。"""
        if not self.is_production:
            return
        secret = self.JWT_SECRET.strip()
        if secret in _FORBIDDEN_PROD_JWT_SECRETS or len(secret) < 32:
            raise RuntimeError(
                "Insecure JWT_SECRET in production environment: "
                "configure a non-placeholder secret with at least 32 characters."
            )

    @property
    def app_timezone(self) -> str:
        """业务时区名称（兼容小写属性访问，空串回退 Asia/Manila）。"""
        return self.APP_TIMEZONE.strip() or "Asia/Manila"

    @property
    def database_url(self) -> str:
        """兼容完整连接串与 DB_* 分段配置；URL.create 会自动转义密码特殊字符。"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return URL.create(
            drivername="mysql+pymysql",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    def resolve_migrate_database_url(self) -> str:
        """优先返回独立 MIGRATE_DATABASE_URL；未配置或为空串时记录告警并回退主连接串。"""
        migrate_url = self.MIGRATE_DATABASE_URL.strip()
        if migrate_url:
            return migrate_url
        logger.warning(
            "MIGRATE_DATABASE_URL is not configured; falling back to primary database connection for migrations."
        )
        return self.database_url


settings = Settings()
