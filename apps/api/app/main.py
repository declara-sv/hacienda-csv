"""FastAPI application: `uv run uvicorn app.main:app --port 5184`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.cors import CORSMiddleware

from app.api import artifacts, catalogs, clients, configs, documents, me, periods, runs, uploads, usage
from app.api.errors import install_error_handlers
from app.config import VERCEL_ORIGIN_PATTERN, Settings, get_settings
from app.security import ClerkTokenVerifier
from app.storage import FileStorage, build_storage
from app.worker import BackgroundWorker

logger = logging.getLogger(__name__)


class _CaseInsensitiveCors(CORSMiddleware):
    """Origins are matched case-insensitively, like the previous API."""

    def is_allowed_origin(self, origin: str) -> bool:
        if origin.lower() in self._allowed_lower:
            return True
        return bool(self.allow_origin_regex is not None and self.allow_origin_regex.fullmatch(origin))

    @property
    def _allowed_lower(self) -> set[str]:
        return {o.lower() for o in self.allow_origins}


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    storage: FileStorage | None = None,
    token_verifier: ClerkTokenVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if session_factory is None:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    storage = storage or build_storage(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker: BackgroundWorker | None = None
        if settings.worker_enabled:
            worker = BackgroundWorker(settings, session_factory, storage)
            worker.start()
        app.state.worker = worker
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    enable_swagger = settings.is_development or settings.enable_swagger
    app = FastAPI(
        title="HaciendaCSV API",
        lifespan=lifespan,
        docs_url="/swagger" if enable_swagger else None,
        redoc_url=None,
        openapi_url="/openapi.json" if enable_swagger else None,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.token_verifier = token_verifier or ClerkTokenVerifier(settings)

    app.add_middleware(
        _CaseInsensitiveCors,
        allow_origins=list(settings.cors_allowed_origins),
        allow_origin_regex=VERCEL_ORIGIN_PATTERN if settings.cors_allow_vercel_subdomains else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"service": "Accounting.Api", "status": "ok", "environment": settings.environment}

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    for module in (me, clients, configs, periods, uploads, documents, runs, artifacts, catalogs, usage):
        app.include_router(module.router)
    return app


app = create_app()

__all__ = ["app", "create_app"]
