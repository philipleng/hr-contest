"""生产安全守门、API 文档开关与 CORS 配置测试"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import create_app


@pytest.mark.parametrize(
    "bad_secret",
    [
        "",
        "   ",
        "short-secret",
        "x" * 31,
        "dev-secret-change-me",
        "your-jwt-secret-here-change-in-production",
        "REPLACE_WITH_RANDOM_LONG_SECRET",
        "test-only-secret-not-for-production",
    ],
)
def test_production_rejects_weak_or_placeholder_jwt_secret(bad_secret):
    cfg = Settings(_env_file=None, APP_ENV="production", JWT_SECRET=bad_secret)
    with pytest.raises(RuntimeError) as exc_info:
        cfg.validate_runtime_security()
    if bad_secret.strip():
        assert bad_secret.strip() not in str(exc_info.value)


def test_production_accepts_strong_jwt_secret():
    strong_secret = "9fK2mP7xQ4vR8wZ1cB5nL3jH6dG0tY2sA"
    cfg = Settings(_env_file=None, APP_ENV="production", JWT_SECRET=strong_secret)
    cfg.validate_runtime_security()


def test_development_allows_default_jwt_secret():
    cfg = Settings(_env_file=None, APP_ENV="development", JWT_SECRET="dev-secret-change-me")
    cfg.validate_runtime_security()


def test_lifespan_blocks_production_startup_with_weak_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "JWT_SECRET", "dev-secret-change-me")
    monkeypatch.setattr(settings, "ENABLE_API_DOCS", False)

    app = create_app()
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_lifespan_allows_production_startup_with_strong_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "JWT_SECRET", "9fK2mP7xQ4vR8wZ1cB5nL3jH6dG0tY2sA")

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json() == {"name": "HR Applicant Pool API"}


def test_api_docs_enabled_defaults_and_overrides():
    assert Settings(_env_file=None, APP_ENV="development").api_docs_enabled is True
    assert Settings(_env_file=None, APP_ENV="production").api_docs_enabled is False
    assert (
        Settings(_env_file=None, APP_ENV="production", ENABLE_API_DOCS=True).api_docs_enabled
        is True
    )
    assert (
        Settings(_env_file=None, APP_ENV="development", ENABLE_API_DOCS=False).api_docs_enabled
        is False
    )


def test_api_docs_disabled_routes(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ENABLE_API_DOCS", False)
    monkeypatch.setattr(settings, "JWT_SECRET", "9fK2mP7xQ4vR8wZ1cB5nL3jH6dG0tY2sA")

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404

        root_resp = client.get("/")
        assert root_resp.status_code == 200
        assert root_resp.json() == {"name": "HR Applicant Pool API"}
        assert "docs" not in root_resp.json()


def test_api_docs_enabled_routes(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ENABLE_API_DOCS", True)
    monkeypatch.setattr(settings, "JWT_SECRET", "9fK2mP7xQ4vR8wZ1cB5nL3jH6dG0tY2sA")

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/").json() == {"name": "HR Applicant Pool API", "docs": "/docs"}


def test_cors_origins_parsing_and_fallbacks():
    assert Settings(_env_file=None, CORS_ORIGINS=" https://hr.example.com , , https://h5.example.com ").cors_origins_list == [
        "https://hr.example.com",
        "https://h5.example.com",
    ]
    assert Settings(_env_file=None, APP_ENV="development", CORS_ORIGINS="").cors_origins_list == ["*"]
    assert Settings(_env_file=None, APP_ENV="development", CORS_ORIGINS=" , , ").cors_origins_list == ["*"]
    assert Settings(_env_file=None, APP_ENV="production", CORS_ORIGINS="").cors_origins_list == []
    assert Settings(_env_file=None, APP_ENV="production", CORS_ORIGINS=" , ").cors_origins_list == []


def test_cors_middleware_applies_configured_origins(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "JWT_SECRET", "9fK2mP7xQ4vR8wZ1cB5nL3jH6dG0tY2sA")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://hr.example.com")

    app = create_app()
    with TestClient(app) as client:
        allowed = client.get("/", headers={"Origin": "https://hr.example.com"})
        assert allowed.headers.get("access-control-allow-origin") == "https://hr.example.com"

        denied = client.get("/", headers={"Origin": "https://evil.example.com"})
        assert "access-control-allow-origin" not in denied.headers
