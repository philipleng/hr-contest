"""测试地基自检：应用能启动、健康检查可用、数据库确实隔离在 SQLite"""


def test_health_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_health_db_error_returns_503(client, db_session, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(db_session, "execute", _boom)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "error"}


def test_docs_available(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_database_is_sqlite_not_production():
    from app.config import settings

    assert settings.database_url.startswith("sqlite")
    assert "mysql" not in settings.database_url
