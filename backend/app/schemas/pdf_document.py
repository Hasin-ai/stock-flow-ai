from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

class QueryType(str, Enum):
    SPECIFIC = "specific"
    GENERAL = "general"
    COMPARATIVE = "comparative"

class DocumentMetadata(BaseModel):
    doc_id: str
    filename: str
    title: Optional[str] = None
    author: Optional[str] = None
    num_pages: int
    created_date: Optional[str] = None
    file_size_kb: float

class DocumentChunk(BaseModel):
    doc_id: str
    chunk_id: str
    page_num: int
    text: str
    embedding_id: Optional[str] = None

class DocumentAnalysis(BaseModel):
    doc_id: str
    summary: str
    key_points: List[str]
    topics: List[str]
    sentiment: Optional[str] = None
    recommendations: Optional[List[str]] = None

class DocumentUploadResponse(BaseModel):
    doc_id: str
    filename: str
    analysis: DocumentAnalysis
    metadata: DocumentMetadata

class DocumentQuery(BaseModel):
    query: str
    doc_id: Optional[str] = None
    query_type: QueryType = QueryType.SPECIFIC

class DocumentQueryResponse(BaseModel):
    query: str
    response: str
    doc_id: Optional[str] = None
    query_type: QueryType
    source_chunks: Optional[List[Dict[str, Any]]] = None