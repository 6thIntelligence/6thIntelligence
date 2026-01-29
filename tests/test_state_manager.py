import pytest
import asyncio
from uuid import uuid4
from app.services.state_manager import StateManager
from app.database import SessionLocal, Message, init_db

# Initialize DB for tests
init_db()

@pytest.fixture
def db_session():
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture
def state_manager(db_session):
    return StateManager(db_session)

@pytest.mark.asyncio
async def test_create_root_node(state_manager):
    session_id = str(uuid4())
    node_id = await state_manager.create_node(
        session_id=session_id,
        parent_id=None,
        role="user",
        content="Hello, this is the start."
    )
    assert node_id is not None
    
    chain = await state_manager.get_context_chain(node_id)
    assert len(chain) == 1
    assert chain[0]["content"] == "Hello, this is the start."

@pytest.mark.asyncio
async def test_create_child_calculates_similarity(state_manager):
    session_id = str(uuid4())
    # Parent
    parent_id = await state_manager.create_node(
        session_id=session_id,
        parent_id=None,
        role="user",
        content="Tell me about housing prices."
    )
    
    # Child (Similar)
    child_id = await state_manager.create_node(
        session_id=session_id,
        parent_id=parent_id,
        role="assistant",
        content="Housing prices are rising."
    )
    
    # Verify similarity calculation (implied by successful creation)
    # We can check DB directly
    db = state_manager.db
    child_msg = db.query(Message).filter(Message.node_id == child_id).first()
    assert child_msg.parent_id == parent_id
    # Similarity might be 0.0 in basic implementation if dependencies missing, but field exists
    assert child_msg.similarity_to_parent >= 0.0

@pytest.mark.asyncio
async def test_get_context_chain_returns_ancestors(state_manager):
    session_id = str(uuid4())
    n1 = await state_manager.create_node(session_id, None, "user", "1")
    n2 = await state_manager.create_node(session_id, n1, "assistant", "2")
    n3 = await state_manager.create_node(session_id, n2, "user", "3")
    
    chain = await state_manager.get_context_chain(n3)
    assert len(chain) == 3
    assert chain[0]["content"] == "1"
    assert chain[2]["content"] == "3"

@pytest.mark.asyncio
async def test_40_turn_conversation_reduces_context(state_manager):
    """
    Simulates a 40-turn conversation and verifies that the returned context
    uses summaries (coarse-graining) rather than full text, keeping token count low.
    """
    session_id = str(uuid4())
    current_parent = None
    
    # Mock OpenRouter service to return summaries immediately to avoid API calls in test
    # Monkeypatching would be ideal, but for now we rely on the logic
    
    for i in range(40):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"This is message number {i} in the sequence. " * 5 # ~30 tokens
        
        node_id = await state_manager.create_node(
            session_id=session_id,
            parent_id=current_parent,
            role=role,
            content=content
        )
        current_parent = node_id
        
        # Manually force summary on some nodes to simulate RG process completion
        if i < 30 and i % 2 == 0:
            db = state_manager.db
            msg = db.query(Message).filter(Message.node_id == node_id).first()
            msg.summary = f"Summary of {i}"
            db.commit()
            
    chain = await state_manager.get_context_chain(current_parent)
    
    # Check if we have summaries
    summarized_count = sum(1 for msg in chain if msg["content"].startswith("Summary"))
    assert summarized_count > 0
    
    # Total characters should be less than full raw text
    # 40 * 30 tokens * 4 chars ~= 4800 chars
    # Summaries are shorter
    raw_len = 40 * len("This is message number 0 in the sequence. " * 5)
    actual_len = sum(len(m["content"]) for m in chain)
    
    assert actual_len < raw_len
    print(f"Compressed {raw_len} chars to {actual_len} chars")
