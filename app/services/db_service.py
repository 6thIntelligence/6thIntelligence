"""
Database Service for Enterprise Bot
Centralized data access layer with validation and error handling
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text
from app.database import SessionLocal, Session, Message, KnowledgeDoc, User

class DatabaseService:
    """Centralized database operations with error handling"""
    
    def __init__(self):
        self._session: Optional[DBSession] = None
    
    def get_session(self) -> DBSession:
        """Get or create database session"""
        if self._session is None:
            self._session = SessionLocal()
        return self._session
    
    def close(self):
        """Close the database session"""
        if self._session:
            self._session.close()
            self._session = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # Session Operations
    def get_chat_session(self, session_id: str) -> Optional[Session]:
        """Get a chat session by ID"""
        db = self.get_session()
        return db.query(Session).filter(Session.id == session_id).first()
    
    def create_chat_session(self, session_id: str = None, name: str = None) -> Session:
        """Create a new chat session"""
        import uuid
        db = self.get_session()
        
        if not session_id:
            session_id = str(uuid.uuid4())
        
        session = Session(id=session_id, name=name or "New Chat")
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    
    def update_session_name(self, session_id: str, name: str) -> Optional[Session]:
        """Update session name"""
        db = self.get_session()
        session = db.query(Session).filter(Session.id == session_id).first()
        if session:
            session.name = name
            db.commit()
            db.refresh(session)
        return session
    
    def delete_chat_session(self, session_id: str) -> bool:
        """Delete a chat session and all its messages"""
        db = self.get_session()
        session = db.query(Session).filter(Session.id == session_id).first()
        if session:
            db.delete(session)
            db.commit()
            return True
        return False
    
    def get_all_sessions(self, limit: int = 100, offset: int = 0) -> List[Session]:
        """Get all chat sessions with pagination"""
        db = self.get_session()
        return db.query(Session).order_by(Session.created_at.desc()).offset(offset).limit(limit).all()
    
    def get_session_count(self) -> int:
        """Get total number of sessions"""
        db = self.get_session()
        return db.query(Session).count()
    
    # Message Operations
    def get_messages(self, session_id: str, limit: int = 100) -> List[Message]:
        """Get messages for a session"""
        db = self.get_session()
        return db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(Message.timestamp).limit(limit).all()
    
    def save_message(
        self, 
        session_id: str, 
        role: str, 
        content: str, 
        tokens: int = 0
    ) -> Message:
        """Save a new message"""
        db = self.get_session()
        
        # Ensure session exists
        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            session = Session(id=session_id, name="New Chat")
            db.add(session)
            db.commit()
        
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            tokens=tokens
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    def get_message_count(self, session_id: str = None) -> int:
        """Get message count for a session or total"""
        db = self.get_session()
        query = db.query(Message)
        if session_id:
            query = query.filter(Message.session_id == session_id)
        return query.count()
    
    def get_recent_messages(self, hours: int = 24, limit: int = 100) -> List[Message]:
        """Get recent messages across all sessions"""
        db = self.get_session()
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return db.query(Message).filter(
            Message.timestamp >= cutoff
        ).order_by(Message.timestamp.desc()).limit(limit).all()
    
    # Knowledge Base Operations
    def get_kb_docs(self) -> List[KnowledgeDoc]:
        """Get all knowledge base documents"""
        db = self.get_session()
        return db.query(KnowledgeDoc).order_by(KnowledgeDoc.upload_date.desc()).all()
    
    def get_kb_doc(self, doc_id: int) -> Optional[KnowledgeDoc]:
        """Get a specific knowledge document"""
        db = self.get_session()
        return db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    
    def add_kb_doc(self, filename: str, content: str) -> KnowledgeDoc:
        """Add a knowledge document"""
        db = self.get_session()
        doc = KnowledgeDoc(filename=filename, content=content)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc
    
    def delete_kb_doc(self, doc_id: int) -> bool:
        """Delete a knowledge document"""
        db = self.get_session()
        doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
        if doc:
            db.delete(doc)
            db.commit()
            return True
        return False
    
    # User Operations
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        db = self.get_session()
        return db.query(User).filter(User.email == email).first()
    
    def create_user(self, email: str, hashed_password: str) -> User:
        """Create a new user"""
        db = self.get_session()
        user = User(email=email, hashed_password=hashed_password)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    # Safe Query Execution
    def execute_safe_query(self, query: str, params: dict = None) -> List[Any]:
        """
        Execute a parameterized query safely.
        Uses SQLAlchemy's text() to prevent SQL injection.
        """
        db = self.get_session()
        result = db.execute(text(query), params or {})
        return result.fetchall()
    
    # Statistics
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        db = self.get_session()
        
        return {
            "total_sessions": db.query(Session).count(),
            "total_messages": db.query(Message).count(),
            "total_kb_docs": db.query(KnowledgeDoc).count(),
            "total_users": db.query(User).count(),
            "messages_today": db.query(Message).filter(
                Message.timestamp >= datetime.utcnow().replace(hour=0, minute=0, second=0)
            ).count(),
            "sessions_today": db.query(Session).filter(
                Session.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
            ).count()
        }
    
    # Health Check
    def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            db = self.get_session()
            db.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

# Singleton instance for convenience
_db_service: Optional[DatabaseService] = None

def get_db_service() -> DatabaseService:
    """Get the database service instance"""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service

def with_db_session(func):
    """Decorator to provide database session"""
    def wrapper(*args, **kwargs):
        with DatabaseService() as db:
            return func(db, *args, **kwargs)
    return wrapper
