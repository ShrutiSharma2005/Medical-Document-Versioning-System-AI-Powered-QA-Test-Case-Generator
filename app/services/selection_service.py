from typing import List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.document import Selection, Node, DocumentVersion
from loguru import logger
import uuid

def reconstruct_selection_text(nodes: List[Node]) -> str:
    """
    Reconstructs the full markdown text from a list of nodes sorted by their sort_order.
    """
    sorted_nodes = sorted(nodes, key=lambda n: n.sort_order)
    blocks = []
    for node in sorted_nodes:
        # If heading is not empty, prefix with appropriate markdown heading level
        if node.heading:
            hashes = "#" * node.level
            blocks.append(f"{hashes} {node.heading}\n{node.text}")
        else:
            blocks.append(node.text)
    return "\n\n".join(blocks).strip()

class SelectionService:
    @staticmethod
    async def create_selection(
        db: AsyncSession, 
        name: str, 
        version_id: str, 
        node_ids: List[str]
    ) -> Selection:
        """
        Creates a new version-pinned selection referencing the specified nodes.
        Verifies that all nodes exist and belong to the correct version.
        """
        logger.info(f"Creating selection '{name}' pinned to version {version_id}...")
        
        # Verify version exists
        version_result = await db.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"Document version {version_id} does not exist.")
            
        # Fetch nodes
        nodes_result = await db.execute(
            select(Node).where(Node.id.in_(node_ids), Node.version_id == version_id)
        )
        nodes = list(nodes_result.scalars().all())
        
        if len(nodes) != len(set(node_ids)):
            found_ids = {n.id for n in nodes}
            missing_ids = set(node_ids) - found_ids
            raise ValueError(f"Some selected node IDs are invalid or belong to a different version: {missing_ids}")
            
        # Create Selection
        selection = Selection(
            id=str(uuid.uuid4()),
            name=name,
            version_id=version_id,
            nodes=nodes
        )
        
        db.add(selection)
        await db.commit()
        
        # Load selection with nodes relation pre-loaded to prevent MissingGreenlet in async context
        result = await db.execute(
            select(Selection).options(selectinload(Selection.nodes)).where(Selection.id == selection.id)
        )
        loaded_selection = result.scalar_one()
        
        logger.info(f"Selection '{name}' (ID: {loaded_selection.id}) created with {len(nodes)} nodes.")
        return loaded_selection

    @staticmethod
    async def get_selection(db: AsyncSession, selection_id: str) -> Optional[Selection]:
        """Retrieves a selection by ID along with its associated nodes."""
        result = await db.execute(
            select(Selection)
            .options(selectinload(Selection.nodes))
            .where(Selection.id == selection_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_selections(db: AsyncSession) -> List[Selection]:
        """Lists all selections."""
        result = await db.execute(
            select(Selection).options(selectinload(Selection.nodes))
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete_selection(db: AsyncSession, selection_id: str) -> bool:
        """Deletes a selection by ID."""
        logger.info(f"Deleting selection {selection_id}...")
        selection = await SelectionService.get_selection(db, selection_id)
        if not selection:
            logger.warning(f"Selection {selection_id} not found for deletion.")
            return False
            
        await db.delete(selection)
        await db.commit()
        logger.info(f"Selection {selection_id} deleted successfully.")
        return True
