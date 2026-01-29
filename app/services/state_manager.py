
import logging
from typing import List, Optional, Tuple
from uuid import UUID, uuid4
import numpy as np
import asyncio
from sqlalchemy.orm import Session
from app.database import Message, SessionLocal
from app.services import openrouter_service, settings_service

logger = logging.getLogger(__name__)

class StateManager:
    """
    Manages Fractal Tree State for long-form conversations.
    Implements coarse-graining (summarization) and hierarchical retrieval.
    """
    
    def __init__(self, db: Session):
        self.db = db
        settings = settings_service.load_settings()
        self.similarity_threshold = settings.get("fractal_similarity_threshold", 0.40)
        self.max_context_tokens = settings.get("max_context_tokens", 4000)

    async def get_context_chain(self, leaf_node_id: str) -> List[dict]:
        """
        Retrieves the ancestor path from the specified leaf node to the root.
        Uses summaries for compressed nodes to preserve context window.
        """
        chain = []
        curr_id = leaf_node_id
        
        while curr_id:
            msg = self.db.query(Message).filter(Message.node_id == curr_id).first()
            if not msg:
                break
            
            # If we have a summary, it's a coarse-grained node
            content = msg.summary if msg.summary else msg.content
            chain.append({"role": msg.role, "content": content})
            curr_id = msg.parent_id
            
        # Return root-first
        return list(reversed(chain))

    async def create_node(self, session_id: str, parent_id: Optional[str], role: str, content: str, tokens: int = 0) -> str:
        """
        Creates a new node in the conversation tree.
        Calculates similarity to parent and triggers coarse-graining if needed.
        """
        new_node_id = str(uuid4())
        similarity = 0.0
        
        if parent_id:
            parent = self.db.query(Message).filter(Message.node_id == parent_id).first()
            if parent:
                # Simple heuristic for similarity if embeddings aren't immediately available
                # In production, we'd use the actual embedding from knowledge_service
                similarity = self._calculate_basic_similarity(content, parent.content)
        
        new_msg = Message(
            session_id=session_id,
            node_id=new_node_id,
            parent_id=parent_id,
            role=role,
            content=content,
            tokens=tokens,
            similarity_to_parent=similarity
        )
        
        self.db.add(new_msg)
        self.db.commit()
        
        # Trigger async coarse-graining if threshold exceeded
        if similarity > self.similarity_threshold:
            asyncio.create_task(self._coarse_grain_node(new_node_id))
            
        return new_node_id

    async def _coarse_grain_node(self, node_id: str):
        """
        Async task to summarize a node and its parent if they are semantically redundant.
        Applied in the Renormalization Group step.
        """
        try:
            # Re-open session in task
            db = SessionLocal()
            node = db.query(Message).filter(Message.node_id == node_id).first()
            if not node or not node.parent_id:
                return
                
            parent = db.query(Message).filter(Message.node_id == node.parent_id).first()
            
            # Request summary from LLM
            prompt = f"Summarize the following interaction into a single concise state for long-term memory:\n\nParent: {parent.content}\n\nChild: {node.content}\n\nSummary:"
            summary = await openrouter_service.generate_fast_summary(prompt) # To be implemented
            
            node.summary = summary
            db.commit()
            db.close()
            logger.info(f"Coarse-grained node {node_id} with parent {node.parent_id}")
        except Exception as e:
            logger.error(f"Coarse-graining failed: {e}")

    def _calculate_basic_similarity(self, text1: str, text2: str) -> float:
        """Heuristic similarity for initial tree branching."""
        # In a real implementation, we'd use the embedding model
        # For the research paper, we assume an embedding-based similarity
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        try:
            tfidf = TfidfVectorizer().fit_transform([text1, text2])
            return float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])
        except:
            return 0.0
