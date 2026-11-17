"""HR 人力池系统 · FastAPI 入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.migrate import run_migrations
from app.routers import applicant, auth, contact, export, health, import_applicant, media, oss, staff


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_runtime_security()
    # AUTO_MIGRATE=true 时先迁移再对外提供服务；失败会中止启动
    run_migrations()
    yield


def create_app() -> FastAPI:
    """构建 FastAPI 应用实例，按当前 settings 控制文档端点与 CORS。"""
    docs_enabled = settings.api_docs_enabled
    application = FastAPI(
        title="HR Applicant Pool API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # 本地开发默认放开 CORS（JWT 走 Authorization 头，不需要 credentials）；
    # 生产由 Nginx 同源托管后可通过 CORS_ORIGINS 收紧或留空
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, prefix="/api")
    application.include_router(auth.router, prefix="/api")
    application.include_router(applicant.router, prefix="/api")
    application.include_router(contact.router, prefix="/api")
    application.include_router(oss.router, prefix="/api")
    application.include_router(media.router, prefix="/api")
    application.include_router(staff.router, prefix="/api")
    application.include_router(export.router, prefix="/api")
    application.include_router(import_applicant.router, prefix="/api")

    @application.get("/")
    def root():
        payload = {"name": "HR Applicant Pool API"}
        if settings.api_docs_enabled:
            payload["docs"] = "/docs"
        return payload

    return application


app = create_app()
