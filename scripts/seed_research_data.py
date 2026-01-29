
import asyncio
from app.database import SessionLocal, Session, Message, User, init_db
from app.services import auth_service
from datetime import datetime
import uuid

async def seed_data():
    print("Initializing Research Database...")
    init_db()
    db = SessionLocal()

    # 1. Seed Researcher Account
    admin_email = "researcher@6thintelligence.ai"
    if not db.query(User).filter(User.email == admin_email).first():
        hashed_pw = auth_service.get_password_hash("research2026")
        db.add(User(email=admin_email, hashed_password=hashed_pw))
        print(f"Created researcher account: {admin_email}")

    # 2. Seed a Sample Research Session
    session_id = str(uuid.uuid4())
    test_session = Session(id=session_id, name="Causal-Fractal Verification Study")
    db.add(test_session)

    # 3. Seed Sample Conversation (Verification Case Study)
    conv_data = [
        ("user", "Explain the 81% reduction in context window tokens.", 0),
        ("assistant", "The reduction is achieved via renormalization coarse-graining. When semantic similarity between nodes exceeds $\lambda=0.4$, they are collapsed into a singular state vector.", 120),
        ("user", "Can we verify the causal path for the 2008 Lehman contagion?", 0),
        ("assistant", "Verified. The Causal Knowledge Graph traces the path: Lehman Brothers Bankruptcy $\\rightarrow$ Global Repo Market Freezes $\\rightarrow$ Greek Sovereign Risk Spikes.", 250)
    ]

    parent_id = None
    for role, content, tokens in conv_data:
        node_id = str(uuid.uuid4())
        msg = Message(
            session_id=session_id,
            node_id=node_id,
            parent_id=parent_id,
            role=role,
            content=content,
            tokens=tokens,
            timestamp=datetime.utcnow()
        )
        db.add(msg)
        parent_id = node_id

    db.commit()
    db.close()
    print("Successfully seeded research database with verification samples.")

if __name__ == "__main__":
    asyncio.run(seed_data())
