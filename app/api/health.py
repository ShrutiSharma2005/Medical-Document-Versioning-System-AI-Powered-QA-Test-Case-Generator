"""
Health check endpoint – SQLite, MongoDB, Groq status.
"""
from fastapi import APIRouter
from app.database.session import engine
from app.database.mongo import mongo_manager
from app.llm.groq_client import check_groq_connectivity
from app.schemas.schemas import HealthResponse
from loguru import logger
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["Health"])

APP_VERSION = "1.0.0"


@router.get("", response_model=HealthResponse, summary="System health check")
async def health_check():
    """
    Returns connectivity status for SQLite, MongoDB, and Groq API.
    Useful for deployment readiness probes.
    """
    logger.info("GET /health – running system checks...")

    # 1. SQLite check
    sqlite_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        sqlite_ok = True
    except Exception as exc:
        logger.error(f"SQLite health check failed: {exc}")

    # 2. MongoDB check
    mongo_ok = await mongo_manager.ping()

    # 3. Groq check
    groq_ok = await check_groq_connectivity()

    overall = "ok" if (sqlite_ok and mongo_ok and groq_ok) else "degraded"
    logger.info(
        f"Health check results – SQLite={sqlite_ok}, "
        f"MongoDB={mongo_ok}, Groq={groq_ok}, Status={overall}"
    )

    return HealthResponse(
        status=overall,
        sqlite=sqlite_ok,
        mongodb=mongo_ok,
        groq=groq_ok,
        version=APP_VERSION,
    )
