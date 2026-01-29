from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime
import uuid

# SQLite database setup
DATABASE_URL = "sqlite:///./6th_intelligence.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    name = Column(String, nullable=True) # E.g., "Chat with John"
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    role = Column(String) # user, assistant, system
    content = Column(Text)
    tokens = Column(Integer, default=0) # Token usage for this message
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Fractal Tree Management Fields
    node_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    parent_id = Column(String, ForeignKey("messages.node_id"), nullable=True)
    summary = Column(Text, nullable=True) # Coarse-grained state
    similarity_to_parent = Column(Float, default=0.0) # Using Float for similarity
    
    session = relationship("Session", back_populates="messages")

class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    content = Column(Text) # Full text content for simple RAG
    upload_date = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Integer, default=1) # Boolean in SQLite is Integer 0/1

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
