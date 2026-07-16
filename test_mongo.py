import asyncio
from app.database.mongo import mongo_manager
from loguru import logger

async def main():
    logger.info("Starting MongoDB test...")
    await mongo_manager.connect()
    logger.info("Connected to MongoDB")

    result = await mongo_manager.collection.insert_one({
        "name": "MongoDB Test",
        "status": "working"
    })

    logger.info(f"Inserted document with id: {result.inserted_id}")
    print(f"Inserted: {result.inserted_id}")

asyncio.run(main())
