import uuid
from datetime import datetime, UTC
from typing import List, Optional
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Table, Column, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base

# Association table for Selection to Node many-to-many relationship
selection_node_association = Table(
    "selection_node",
    Base.metadata,
    Column("selection_id", String(36), ForeignKey("selections.id", ondelete="CASCADE"), primary_key=True),
    Column("node_id", String(36), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True),
)

class Document(Base):
    __tablename__ = "documents"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    
    # Relationships
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_num"
    )

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_num: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active")  # e.g., active, superseded
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    
    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="versions")
    nodes: Mapped[List["Node"]] = relationship(
        "Node", back_populates="version", cascade="all, delete-orphan", order_by="Node.sort_order"
    )
    selections: Mapped[List["Selection"]] = relationship(
        "Selection", back_populates="version", cascade="all, delete-orphan"
    )

class Node(Base):
    __tablename__ = "nodes"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    heading: Mapped[str] = mapped_column(String(500), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    
    # Relationships
    version: Mapped[DocumentVersion] = relationship("DocumentVersion", back_populates="nodes")
    parent: Mapped[Optional["Node"]] = relationship("Node", remote_side=[id], back_populates="children")
    children: Mapped[List["Node"]] = relationship("Node", back_populates="parent", cascade="all, delete-orphan", order_by="Node.sort_order")
    
    selections: Mapped[List["Selection"]] = relationship(
        "Selection", secondary=selection_node_association, back_populates="nodes"
    )

class Selection(Base):
    __tablename__ = "selections"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    
    # Relationships
    version: Mapped[DocumentVersion] = relationship("DocumentVersion", back_populates="selections")
    nodes: Mapped[List[Node]] = relationship(
        "Node", secondary=selection_node_association, back_populates="selections"
    )

class VersionComparison(Base):
    __tablename__ = "version_comparisons"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    to_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    diff_data: Mapped[dict] = mapped_column(JSON, nullable=False)  # JSON structure outlining differences
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

class NodeMapping(Base):
    __tablename__ = "node_mappings"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)
    comparison_status: Mapped[str] = mapped_column(String(50), nullable=False)  # unchanged, modified, deleted
    diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
