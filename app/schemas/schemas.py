from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ───────────────────────────────────────────────
# Node Schemas
# ───────────────────────────────────────────────

class NodeBase(BaseModel):
    heading: str
    level: int
    text: str
    content_hash: str
    sort_order: int

class NodeResponse(NodeBase):
    id: str
    version_id: str
    parent_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class NodeTreeResponse(NodeResponse):
    children: List["NodeTreeResponse"] = Field(default_factory=list)

NodeTreeResponse.model_rebuild()


# ───────────────────────────────────────────────
# Document Schemas
# ───────────────────────────────────────────────

class DocumentVersionResponse(BaseModel):
    id: str
    document_id: str
    version_num: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

class DocumentResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    versions: List[DocumentVersionResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

class DocumentVersionDetail(DocumentVersionResponse):
    nodes: List[NodeResponse] = Field(default_factory=list)


# ───────────────────────────────────────────────
# Selection Schemas
# ───────────────────────────────────────────────

class SelectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    version_id: str
    node_ids: List[str] = Field(..., min_length=1)

class SelectionResponse(BaseModel):
    id: str
    name: str
    version_id: str
    created_at: datetime
    nodes: List[NodeResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ───────────────────────────────────────────────
# LLM Test Case Schemas (Pydantic v2)
# ───────────────────────────────────────────────

class TestCase(BaseModel):
    test_case_id: str
    title: str
    requirement_reference: str
    preconditions: str
    steps: List[str]
    expected_result: str
    priority: str
    risk_level: str
    category: str

class TestCaseList(BaseModel):
    test_cases: List[TestCase]


# ───────────────────────────────────────────────
# Generation Schemas (MongoDB)
# ───────────────────────────────────────────────

class GenerationTrigger(BaseModel):
    selection_id: str

class StalenessInfo(BaseModel):
    is_stale: bool
    stale_reason: Optional[str] = None
    changed_headings: List[str] = Field(default_factory=list)
    diff_summaries: List[str] = Field(default_factory=list)

class GenerationResponse(BaseModel):
    id: str
    selection_id: str
    version_id: str
    llm_model: str
    generated_at: datetime
    status: str  # CURRENT, STALE, FAILED
    stale_reason: Optional[str] = None
    response_time: Optional[float] = None
    test_cases: List[TestCase] = Field(default_factory=list)
    staleness_info: Optional[StalenessInfo] = None


# ───────────────────────────────────────────────
# Version Comparison Schemas
# ───────────────────────────────────────────────

class ComparisonSummary(BaseModel):
    from_version_id: str
    to_version_id: str
    added_count: int
    deleted_count: int
    modified_count: int
    unchanged_count: int
    total_v1: int
    total_v2: int


# ───────────────────────────────────────────────
# Search Schemas
# ───────────────────────────────────────────────

class SearchResult(BaseModel):
    node_id: str
    version_id: str
    heading: str
    level: int
    snippet: str
    match_type: str  # "heading" or "body"


# ───────────────────────────────────────────────
# Health Schema
# ───────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    sqlite: bool
    mongodb: bool
    groq: bool
    version: str
