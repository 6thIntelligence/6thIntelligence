from pydantic import BaseModel
from typing import List, Optional

class ContextNode(BaseModel):
    node_id: str
    parent_id: Optional[str] = None
    role: str
    content: str
    summary: Optional[str] = None
    similarity_to_parent: float = 0.0
    tokens: int = 0
    children: List['ContextNode'] = []
    
    class Config:
        from_attributes = True
