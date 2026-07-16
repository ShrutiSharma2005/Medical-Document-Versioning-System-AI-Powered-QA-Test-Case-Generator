"""
MongoDB repository for generated test cases (CRUD + staleness updates).
"""
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from loguru import logger


def _serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Converts MongoDB ObjectId to a plain string id for serialization."""
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


class GenerationRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.col = collection

    async def insert(self, record: Dict[str, Any]) -> str:
        """Inserts a new generation record, returns the inserted document id."""
        result = await self.col.insert_one(record)
        logger.info(f"Inserted generation record with id: {result.inserted_id}")
        return str(result.inserted_id)

    async def get_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a generation record by its MongoDB ObjectId string."""
        try:
            doc = await self.col.find_one({"_id": ObjectId(record_id)})
        except Exception:
            doc = None
        return _serialize_doc(doc)

    async def get_by_selection_id(self, selection_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent generation for a given selection_id."""
        doc = await self.col.find_one(
            {"selection_id": selection_id},
            sort=[("generated_at", -1)],
        )
        return _serialize_doc(doc)

    async def list_by_node_id(self, node_id: str) -> List[Dict[str, Any]]:
        """Returns all generations that reference a given node_id in node_hashes."""
        cursor = self.col.find(
            {f"node_hashes.{node_id}": {"$exists": True}},
            sort=[("generated_at", -1)],
        )
        docs = await cursor.to_list(length=None)
        return [_serialize_doc(d) for d in docs]

    async def list_all(self) -> List[Dict[str, Any]]:
        """Returns all generation records ordered by newest first."""
        cursor = self.col.find({}, sort=[("generated_at", -1)])
        docs = await cursor.to_list(length=None)
        return [_serialize_doc(d) for d in docs]

    async def update_status(
        self,
        selection_id: str,
        status: str,
        stale_reason: Optional[str] = None,
    ) -> int:
        """
        Updates the status (and optionally stale_reason) for all generation
        records that match the given selection_id.
        Returns the count of modified documents.
        """
        update_fields: Dict[str, Any] = {
            "status": status,
            "stale_checked_at": datetime.now(timezone.utc),
        }
        if stale_reason is not None:
            update_fields["stale_reason"] = stale_reason

        result = await self.col.update_many(
            {"selection_id": selection_id},
            {"$set": update_fields},
        )
        logger.info(
            f"Updated status to '{status}' for {result.modified_count} "
            f"record(s) with selection_id={selection_id}."
        )
        return result.modified_count
