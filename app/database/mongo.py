from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import settings
from loguru import logger

class MongoManager:
    def __init__(self):
        self.client: AsyncIOMotorClient = None
        self.db = None
        self.collection = None

    async def connect(self):
        """Initialize motor client connection."""
        if not self.client:
            logger.info(f"Connecting to MongoDB at {settings.MONGO_URI}...")
            self.client = AsyncIOMotorClient(settings.MONGO_URI)
            self.db = self.client[settings.MONGO_DB_NAME]
            self.collection = self.db[settings.MONGO_COLLECTION]
            # Verify connection by pinging the server
            await self.db.command("ping")
            logger.info("MongoDB client initialized and connected.")

    async def disconnect(self):
        """Close motor client connection."""
        if self.client:
            logger.info("Closing MongoDB connection...")
            self.client.close()
            self.client = None
            self.db = None
            self.collection = None
            logger.info("MongoDB connection closed.")

    async def ping(self) -> bool:
        """Ping MongoDB to verify active connection."""
        if not self.client:
            return False
        try:
            # The ismaster command is cheap and does not require auth.
            await self.db.command("ping")
            return True
        except Exception as e:
            logger.error(f"MongoDB ping failed: {e}")
            return False

# Global instance of MongoManager
mongo_manager = MongoManager()
