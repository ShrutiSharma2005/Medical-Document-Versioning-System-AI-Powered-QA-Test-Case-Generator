"""
FastAPI application factory – wires up routers, lifespan events, middleware, and logging.
"""
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config.settings import settings
from app.database.init_db import init_sqlite_db
from app.database.mongo import mongo_manager
from app.api import documents, versions, nodes, search, selections, generated, health


# ── Logging ──────────────────────────────────────────────────────────────── #

logger.remove()
logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> – "
        "<level>{message}</level>"
    ),
    colorize=True,
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    enqueue=True,
)


# ── Lifespan ─────────────────────────────────────────────────────────────── #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle management."""
    logger.info("Starting up Tri9t AI Backend...")
    await init_sqlite_db()
    await mongo_manager.connect()
    logger.info("Application ready.")
    yield
    logger.info("Shutting down...")
    await mongo_manager.disconnect()


# ── Application factory ───────────────────────────────────────────────────── #

def create_app() -> FastAPI:
    app = FastAPI(
        title="Tri9t AI – Document Versioning & QA Test Case Generator",
        description=(
            "A production-ready backend for parsing technical documentation, "
            "versioning it, creating node selections, generating QA test cases via "
            "Groq LLM, and detecting stale outputs when documentation changes."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS (allow all for development – tighten in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected internal error occurred."},
        )

    # Mount all routers under /api/v1
    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(versions.router, prefix=prefix)
    app.include_router(nodes.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(selections.router, prefix=prefix)
    app.include_router(generated.router, prefix=prefix)

    return app


app = create_app()
