"""pytest 公共夹具：SQLite 内存库 + 每用例事务回滚

三条硬约束（对应 AGENTS.md「云端运行环境」）：
1. 必须在导入 app.config 之前注入 DATABASE_URL / JWT_SECRET；
2. 导入配置时把工作目录切到临时目录，确保 pydantic-settings 的 `.env` 读不到任何文件；
3. 测试进程内的数据库必须不是 MySQL / 生产库（见 _assert_not_production）。
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 1) 环境变量先行：优先于任何 .env
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-only-secret-not-for-production"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRE_HOURS"] = "1"
# 防止 DATABASE_URL 为空时回退到 DB_* 分段配置
for _key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
    os.environ.pop(_key, None)

# 2) 在临时目录里导入配置，Settings 的 env_file=".env" 因此读不到 backend/.env
_original_cwd = os.getcwd()
os.chdir(tempfile.mkdtemp(prefix="hr-tests-"))
try:
    import app.config  # noqa: F401,E402
finally:
    os.chdir(_original_cwd)

from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.mysql import TINYINT  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.database as app_db  # noqa: E402
from app.models import Base, Staff  # noqa: E402
from app.utils.security import create_access_token, hash_password  # noqa: E402

TEST_PASSWORD = "test-password-123"


@compiles(TINYINT, "sqlite")
def _tinyint_to_integer(element, compiler, **kw):
    """模型用 MySQL TINYINT，SQLite 不认识；测试建表时降级为 INTEGER"""
    return "INTEGER"


@compiles(BigInteger, "sqlite")
def _bigint_to_integer(element, compiler, **kw):
    """BIGINT 主键在 SQLite 下不会成为 rowid 别名，自增会失败；降级为 INTEGER"""
    return "INTEGER"


TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

TEST_ENGINE = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# app.database 在导入时已按 settings 建过一次 engine，这里替换成测试引擎
app_db.engine = TEST_ENGINE
app_db.SessionLocal.configure(bind=TEST_ENGINE)


def _dedupe_index_names() -> None:
    """MySQL 的索引名只在表内唯一，SQLite 是库内唯一；建表前给重名索引加表前缀"""
    seen: set[str] = set()
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            if index.name in seen:
                index.name = f"{table.name}_{index.name}"
            seen.add(index.name)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    _dedupe_index_names()
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture()
def db_session():
    """每个用例一个外层事务，结束回滚；应用代码里的 commit 只提交 savepoint"""
    connection = TEST_ENGINE.connect()
    transaction = connection.begin()
    # pysqlite 默认不会真正开启事务，若不补 BEGIN，后面的 SAVEPOINT 会成为最外层
    # 事务，RELEASE 时数据直接落库，跨用例污染。显式 BEGIN 后 savepoint 才是嵌套的。
    connection.exec_driver_sql("BEGIN")
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        autocommit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def staff_password() -> str:
    """测试员工统一密码（配合 make_staff / 登录用例）"""
    return TEST_PASSWORD


@pytest.fixture()
def make_staff(db_session):
    """员工工厂：直接落库，绕过 StaffCreateRequest 的 role 枚举限制"""

    def _make(
        username: str,
        role: str = "staff",
        status: str = "active",
        real_name: str | None = None,
        password: str = TEST_PASSWORD,
    ) -> Staff:
        staff = Staff(
            username=username,
            password_hash=hash_password(password),
            real_name=real_name or username,
            role=role,
            status=status,
        )
        db_session.add(staff)
        db_session.commit()
        db_session.refresh(staff)
        return staff

    return _make


@pytest.fixture()
def make_token():
    """给员工签发真实 JWT（不经过登录接口，避免触发登录限流）"""

    def _make(staff: Staff) -> str:
        return create_access_token({
            "sub": str(staff.id),
            "username": staff.username,
            "role": staff.role,
        })

    return _make


@pytest.fixture()
def make_auth_headers(make_token):
    def _make(staff: Staff) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(staff)}"}

    return _make


def pytest_configure(config):
    """注册 slow 标记：大数据量用例（如导出万行）默认也跑，CI 可 -m "not slow" 跳过"""
    config.addinivalue_line("markers", "slow: 耗时明显高于其他用例的大数据量测试")


@pytest.fixture()
def admin_headers(make_staff, make_auth_headers):
    """每用例一个启用 admin 的 Authorization 头"""
    return make_auth_headers(make_staff("admin_case", role="admin"))


@pytest.fixture()
def staff_headers(make_staff, make_auth_headers):
    """每用例一个启用 staff 的 Authorization 头"""
    return make_auth_headers(make_staff("staff_case", role="staff"))


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """清空进程内限流桶与每日配额：按 IP 计数且跨用例共享，不重置会互相干扰"""
    from app.utils.ratelimit import _buckets, _daily

    _buckets.clear()
    _daily.clear()
    yield


@pytest.fixture()
def submit_payload():
    """构造最小合法提交体（SUB/EXP 共用），可按需覆盖字段"""

    def _make(**overrides) -> dict:
        payload = {
            "privacy_agreed": True,
            "first_name": "Juan",
            "last_name": "Dela Cruz",
            "phone": "09171234567",
        }
        payload.update(overrides)
        return payload

    return _make


@pytest.fixture(autouse=True)
def _assert_not_production():
    """守门：任何用例都不允许把数据库指向 MySQL"""
    from app.config import settings

    assert settings.database_url.startswith("sqlite"), settings.database_url
    assert "mysql" not in settings.database_url
    yield
