"""
Document and Node repository wrapping SQLAlchemy async queries.
"""
from typing import List, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func, or_
from app.models.document import (
    Document,
    DocumentVersion,
    Node,
    VersionComparison,
    NodeMapping,
)
from loguru import logger


class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document(self, title: str) -> Document:
        doc = Document(title=title)
        self.db.add(doc)
        await self.db.flush()
        logger.info(f"Created Document '{title}' id={doc.id}")
        return doc

    async def get_document(self, doc_id: str) -> Optional[Document]:
        result = await self.db.execute(
            select(Document)
            .options(selectinload(Document.versions))
            .where(Document.id == doc_id)
        )
        return result.scalar_one_or_none()

    async def list_documents(self) -> List[Document]:
        result = await self.db.execute(
            select(Document).options(selectinload(Document.versions))
        )
        return list(result.scalars().all())

    async def get_version(self, version_id: str) -> Optional[DocumentVersion]:
        result = await self.db.execute(
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.nodes))
            .where(DocumentVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_version(self, document_id: str) -> Optional[DocumentVersion]:
        result = await self.db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_num.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_versions(self) -> List[DocumentVersion]:
        result = await self.db.execute(
            select(DocumentVersion).order_by(DocumentVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_version(self, document_id: str, version_num: int) -> DocumentVersion:
        ver = DocumentVersion(document_id=document_id, version_num=version_num)
        self.db.add(ver)
        await self.db.flush()
        logger.info(f"Created DocumentVersion {version_num} id={ver.id}")
        return ver

    async def create_nodes_bulk(self, node_dicts: List[dict]) -> List[Node]:
        nodes = [Node(**nd) for nd in node_dicts]
        self.db.add_all(nodes)
        await self.db.flush()
        logger.info(f"Bulk-inserted {len(nodes)} nodes.")
        return nodes

    async def get_node(self, node_id: str) -> Optional[Node]:
        result = await self.db.execute(
            select(Node).where(Node.id == node_id)
        )
        return result.scalar_one_or_none()

    async def get_node_children(self, node_id: str) -> List[Node]:
        result = await self.db.execute(
            select(Node)
            .where(Node.parent_id == node_id)
            .order_by(Node.sort_order)
        )
        return list(result.scalars().all())

    async def get_nodes_by_version(self, version_id: str) -> List[Node]:
        result = await self.db.execute(
            select(Node)
            .where(Node.version_id == version_id)
            .order_by(Node.sort_order)
        )
        return list(result.scalars().all())

    async def search_nodes(
        self, query: str, document_id: Optional[str] = None
    ) -> List[Node]:
        """Full-text search across node headings and body text."""
        like_q = f"%{query}%"
        stmt = select(Node).where(
            or_(Node.heading.ilike(like_q), Node.text.ilike(like_q))
        )
        if document_id:
            # Join through DocumentVersion to filter by document
            stmt = stmt.join(
                DocumentVersion, Node.version_id == DocumentVersion.id
            ).where(DocumentVersion.document_id == document_id)
        stmt = stmt.order_by(Node.sort_order)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def save_version_comparison(
        self,
        from_version_id: str,
        to_version_id: str,
        diff_data: dict,
        node_mappings: List[dict],
    ) -> VersionComparison:
        """Persists a VersionComparison and associated NodeMapping records."""
        comparison = VersionComparison(
            from_version_id=from_version_id,
            to_version_id=to_version_id,
            diff_data=diff_data,
        )
        self.db.add(comparison)

        mapping_objs = [NodeMapping(**m) for m in node_mappings]
        self.db.add_all(mapping_objs)
        await self.db.flush()

        logger.info(
            f"Saved VersionComparison id={comparison.id} "
            f"with {len(mapping_objs)} node mappings."
        )
        return comparison

    async def get_node_mappings_for_node(self, node_id: str) -> List[NodeMapping]:
        """Returns all NodeMapping records where from_node_id = node_id."""
        result = await self.db.execute(
            select(NodeMapping).where(NodeMapping.from_node_id == node_id)
        )
        return list(result.scalars().all())

    async def get_latest_comparison_for_document(
        self, document_id: str
    ) -> Optional[VersionComparison]:
        """Returns the most recent comparison involving versions of a document."""
        result = await self.db.execute(
            select(VersionComparison)
            .join(
                DocumentVersion,
                VersionComparison.from_version_id == DocumentVersion.id,
            )
            .where(DocumentVersion.document_id == document_id)
            .order_by(VersionComparison.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
