from app.database.session import engine, Base
# Import models to register them on Base.metadata
from app.models.document import Document, DocumentVersion, Node, Selection, VersionComparison, NodeMapping
from loguru import logger

async def init_sqlite_db():
    """Initializes SQLite database schemas."""
    logger.info("Initializing SQLite database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SQLite database tables initialized successfully.")
