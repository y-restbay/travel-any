from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

# 把项目根/后端目录的 .env 注入 os.environ，让工具层 (QWEATHER_KEY 等) 能 os.getenv 取到。
# pydantic-settings 只把 .env 映射到 Settings 字段，不会写回 os.environ，所以这一步必须显式做。
# override=False 保证已经手动 export 的变量优先。
load_dotenv(override=False)

from app.api import admin, chat, exports, health, rag, uploads
from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import run_lightweight_migrations
from app.db.session import SessionLocal, engine
from app.models import booking as booking_models  # noqa: F401  注册业务表
from app.models import config as config_models  # noqa: F401
from app.services.config_service import ensure_defaults


settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    app.include_router(rag.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)
    app.include_router(exports.router, prefix=settings.api_prefix)
    app.include_router(uploads.router, prefix=settings.api_prefix)

    Instrumentator(
        excluded_handlers=["/metrics"],
        should_instrument_requests_inprogress=True,
    ).instrument(app).expose(app, include_in_schema=False, should_gzip=True)

    @app.on_event("startup")
    def on_startup() -> None:
        from app.services.log_buffer import install_log_buffer

        install_log_buffer()
        Base.metadata.create_all(bind=engine)
        run_lightweight_migrations(engine)
        with SessionLocal() as db:
            ensure_defaults(db)

    return app


app = create_app()
