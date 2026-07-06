from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class QueryRequest(BaseModel):
    query: str = Field(..., description="The user query or question to be answered by the RAG system.")
    session_id: str = Field(default="default-session", description="Conversation session ID for memory context.")
    use_cache: bool = Field(default=True, description="Flag to bypass or use the semantic cache.")

class SearchDocument(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0

class QueryResponse(BaseModel):
    answer: str = Field(..., description="The generated response from the assistant.")
    sources: List[SearchDocument] = Field(default_factory=list, description="List of source documents referenced.")
    cached: bool = Field(default=False, description="Indicates if the query was resolved via semantic cache.")
    latency_ms: float = Field(default=0.0, description="Time taken to resolve the request.")
