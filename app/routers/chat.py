from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import asyncio
import os
import time
from sqlalchemy.orm import Session
from app.services import settings_service, openrouter_service
from app.services import security_service, logging_service, metrics_service
from app.services import handover_service, cost_service, feedback_service
from app.services import handover_service, cost_service, feedback_service
from app import database
from app.database import SessionLocal
from openai import AsyncOpenAI
import pandas as pd
from app.services.state_manager import StateManager
from app.services.causal_service import CausalService

# Initialize Causal Service (Singleton)
causal_service = CausalService()

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    parent_node_id: Optional[str] = None # For Fractal Tree traversal

@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    # Create new session ID if one doesn't exist in cookie or query
    # For simplicity, we'll let the frontend generate/manage session ID or passed via query
    # But usually server generates it.
    import uuid
    new_session_id = str(uuid.uuid4())
    return templates.TemplateResponse("chat.html", {"request": request, "session_id": new_session_id})

@router.get("/widget", response_class=HTMLResponse)
async def widget_page(request: Request):
    import uuid
    new_session_id = str(uuid.uuid4())
    return templates.TemplateResponse("widget.html", {"request": request, "session_id": new_session_id})

@router.get("/demo", response_class=HTMLResponse)
async def demo_page(request: Request):
    return templates.TemplateResponse("demo.html", {"request": request})

@router.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str, db: Session = Depends(database.get_db)):
    msgs = db.query(database.Message).filter(database.Message.session_id == session_id).order_by(database.Message.timestamp).all()
    return {"messages": [{"role": m.role, "content": m.content} for m in msgs]}

@router.get("/api/chat/sessions")
async def get_sessions(db: Session = Depends(database.get_db)):
    # Return list of sessions, newest first
    sessions = db.query(database.Session).order_by(database.Session.created_at.desc()).all()
    return {"sessions": [{"id": s.id, "name": s.name or "New Chat", "created_at": s.created_at.isoformat()} for s in sessions]}

@router.post("/api/chat")
async def chat_endpoint(req: ChatRequest, session_id: Optional[str] = None):
    # Track response time
    start_time = time.time()
    
    # Ensure session exists
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
    
    # Get last user message
    last_msg = req.messages[-1]
    user_content = last_msg.content
    
    # Security Check: Validate and sanitize input
    sanitized_content = security_service.sanitize_input(user_content)
    
    # Check for prompt injection
    is_injection, confidence, patterns = security_service.detect_prompt_injection(sanitized_content)
    if is_injection and confidence > 0.8:
        logging_service.log_security_event(
            "prompt_injection_blocked",
            severity="warning",
            context={"session_id": session_id, "confidence": confidence}
        )
        raise HTTPException(status_code=400, detail="Invalid input detected. Please rephrase your message.")
    
    # Check for SQL injection (extra safety)
    sql_detected, _ = security_service.detect_sql_injection(sanitized_content)
    if sql_detected:
        logging_service.log_security_event(
            "sql_injection_blocked",
            severity="critical",
            context={"session_id": session_id}
        )
        raise HTTPException(status_code=400, detail="Invalid input detected.")

    settings = settings_service.load_settings()
    api_key = settings.get("openrouter_api_key")
    model = settings.get("model")
    system_persona = settings.get("system_persona")
    temperature = settings.get("temperature", 0.7)
    
    # Delay Logic
    min_delay = settings.get("response_delay_min", 0.0)
    max_delay = settings.get("response_delay_max", 0.0)
    
    # Delay Logic REMOVED for performance optimization
    # if max_delay > 0:
    #     import random
    #     sleep_time = random.uniform(min_delay, max_delay)
    #     await asyncio.sleep(sleep_time)

    if not api_key:
        raise HTTPException(status_code=400, detail="API Key not configured in Admin/Settings")
    
    # DB Session and State Management
    db_gen = database.get_db()
    db = next(db_gen)
    state_manager = StateManager(db)

    # 1. Fractal Tree Context Retrieval
    # If parent_node_id is provided, we walk the tree. 
    # Otherwise, we use the provided message history (backward compatibility).
    if req.parent_node_id:
        tree_context = await state_manager.get_context_chain(req.parent_node_id)
        # Convert tree context to the format expected by LLM
        messages_to_send = tree_context
    else:
        # Fallback to linear history if no tree node specified
        messages_to_send = [{"role": m.role, "content": m.content} for m in req.messages[:-1]]

    # Save User message to Tree
    user_node_id = await state_manager.create_node(
        session_id=session_id,
        parent_id=req.parent_node_id,
        role="user",
        content=user_content
    )

    # Vector Search RAG: Query for relevant context
    from app.services import knowledge_service
    # Use async query to avoid blocking
    raw_context_list = await knowledge_service.query_knowledge_async(user_content, n_results=10)
    
    # 2. Causal Verification Layer (Reranking)
    # Split the formatted context back into chunks if possible, or just pass text
    # knowledge_service.query_knowledge returns a string with '---' delimiters
    chunks = [c.strip() for c in raw_context_list.split("---") if c.strip()]
    verified_chunks = causal_service.verify_mechanisms(user_content, chunks)
    
    context_text = ""
    if verified_chunks:
        context_text = "\n\nVerified Causal Context:\n" + "\n---\n".join(verified_chunks) + "\n"

    
    
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Enterprise AI Chatbot",
        }
    )

    # Prepare messages
    # Inject RAG context into system prompt
    
    # STATIC CORE IDENTITY (Regardless of Admin Settings)
    static_identity = (
        "Your name is Abayomi. You work for ExpertListing. "
        "You speak like a human team member. "
        "You never mention AI, bots, models, or systems. "
        "Reply length: Use few lines only. Write like a real person. Stop once the question gets answered. "
        "Style: Clear language. Short sentences. Direct tone. No filler talk. "
        "Behavior: Address users as you and your. Answer property questions fast. "
        "Share prices, locations, and verified facts. "
        "If someone asks for a price, check the knowledge base carefully. Always ask them if they want to rent or buy. "
    )
    
    guardrails = "\nSTRICT: Identity Human. No AI references. No guessing. If data missing, state team referral as a human colleague."
    final_system_prompt = static_identity + "\n\nAdditional Data:\n" + system_persona + context_text + guardrails
    
    messages = [{"role": "system", "content": final_system_prompt}]
    messages.extend(messages_to_send)
    messages.append({"role": "user", "content": user_content})
    
    # Pre-generate AI Node ID to include in headers
    ai_node_id = str(uuid.uuid4())
    
    async def event_generator():
        # Attempt 1: Standard System Prompt
        current_messages = messages
        full_response = ""
        
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=current_messages,
                temperature=temperature,
                stream=True,
                extra_body={
                    "provider": { "data_collection": "allow" },
                    "include_reasoning": True
                }
            )
            async for chunk in stream:
                 content = chunk.choices[0].delta.content or ""
                 if content:
                     full_response += content
                     yield content

        except Exception as e:
            # (Fallback logic stays same)
            err_str = str(e)
            
            # Fallback for models that reject "system" role (Google/Gemini often)
            if "Developer instruction" in err_str or "system message" in err_str.lower():
                try:
                    # Retry logic (abbreviated for brevity, same as before but capturing response)
                     # Find system message
                    sys_msg = next((m for m in messages if m["role"] == "system"), None)
                    if sys_msg:
                        fallback_messages = [m for m in messages if m["role"] != "system"]
                        if fallback_messages and fallback_messages[0]["role"] == "user":
                            fallback_messages[0]["content"] = f"System Instructions: {sys_msg['content']}\n\nUser Query: {fallback_messages[0]['content']}"
                        else:
                            fallback_messages.insert(0, {"role": "user", "content": f"System Instructions: {sys_msg['content']}"})
                            
                        # Retry Call
                        stream = await client.chat.completions.create(
                            model=model,
                            messages=fallback_messages,
                            temperature=temperature,
                            stream=True,
                            extra_body={
                                "provider": { "data_collection": "allow" },
                                "include_reasoning": True
                            }
                        )
                        async for chunk in stream:
                             content = chunk.choices[0].delta.content or ""
                             if content:
                                 full_response += content
                                 yield content
                except Exception as retry_err:
                    err_str = str(retry_err)

            if not full_response: # If we didn't output anything due to error
                if "404" in err_str and "data policy" in err_str:
                    yield "\n[System Error: The selected model is not available with your current OpenRouter data privacy settings.]"
                else:
                    yield f"\n[Error: {err_str}]"
        
        # Log AI Response to DB and track metrics
        if session_id and full_response:
            try:
                 # Estimate tokens: ~4 chars per token
                 token_count = len(full_response) // 4
                 input_tokens = sum(len(m.content) // 4 for m in req.messages)
                 
                 # Calculate response time
                 response_time_ms = (time.time() - start_time) * 1000
                 
                 # Re-acquire DB session thread-safe
                 db_sess = SessionLocal() 
                 
                 # Save AI Response to Tree using the pre-generated ID
                 ai_msg = database.Message(
                     session_id=session_id,
                     node_id=ai_node_id,
                     parent_id=user_node_id,
                     role="assistant",
                     content=full_response,
                     tokens=token_count
                 )
                 db_sess.add(ai_msg)
                 db_sess.commit()
                 db_sess.close()
                 
                 # Record metrics
                 metrics_service.record_response_time(session_id, response_time_ms, model)
                 metrics_service.record_token_usage(session_id, input_tokens, token_count, model)
                 
                 # Record cost
                 cost_service.record_usage(model, input_tokens, token_count, session_id)
                 
                 # Log chat interaction
                 logging_service.log_chat_interaction(
                     session_id=session_id,
                     user_message=user_content,
                     ai_response=full_response[:200] + "..." if len(full_response) > 200 else full_response,
                     tokens_used=token_count,
                     response_time_ms=response_time_ms,
                     model=model
                 )
            except Exception as db_err:
                logging_service.log_error(
                    error_type="db_save_error",
                    message=str(db_err),
                    context={"session_id": session_id}
                )

    return StreamingResponse(
        event_generator(), 
        media_type="text/plain",
        headers={
            "X-Session-ID": session_id,
            "X-User-Node-ID": user_node_id,
            "X-Assistant-Node-ID": ai_node_id
        }
    )

@router.post("/api/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    try:
        content = await file.read()
        
        # Basic Text Extraction
        text_content = ""
        filename = file.filename.lower()
        
        if filename.endswith(".pdf"):
            import io, PyPDF2
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            for page in pdf_reader.pages:
                text_content += page.extract_text() + "\n"
        elif filename.endswith(".docx"):
            import io, docx
            doc = docx.Document(io.BytesIO(content))
            for para in doc.paragraphs:
                text_content += para.text + "\n"
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            import io
            # Read Excel file
            df = pd.read_excel(io.BytesIO(content))
            # Convert to string (CSV format often best for RAG context)
            text_content = df.to_csv(index=False)
            
        elif filename.endswith(".txt") or filename.endswith(".md") or filename.endswith(".js") or filename.endswith(".json") or filename.endswith(".csv"):
             text_content = content.decode("utf-8")
        else:
             # Fallback
             try:
                 text_content = content.decode("utf-8")
             except:
                 text_content = "[Binary or Unsupported File Content]"

        # Save to Knowledge Base DB
        kb_doc = database.KnowledgeDoc(filename=file.filename, content=text_content)
        db.add(kb_doc)
        db.commit()
        db.refresh(kb_doc)
        
        # Index in ChromaDB for fast vector search
        from app.services import knowledge_service
        knowledge_service.add_document(
            doc_id=str(kb_doc.id),
            text=text_content,
            metadata={"filename": file.filename, "source_id": str(kb_doc.id)}
        )
        
        # Also save to disk for safekeeping
        import os
        os.makedirs("data/uploads", exist_ok=True)
        file_path = f"data/uploads/{file.filename}"
        with open(file_path, "wb") as f:
            f.write(content)
            
        return {"filename": file.filename, "status": "uploaded", "message": "File processed and added to vector knowledge base."}
    except Exception as e:
        logging_service.log_error(
            "file_upload_error",
            str(e),
            context={"filename": file.filename}
        )
        raise HTTPException(status_code=500, detail=str(e))

class FeedbackRequest(BaseModel):
    session_id: str
    rating: int  # 1-5
    category: Optional[str] = None  # response_quality, speed, accuracy, helpfulness
    comment: Optional[str] = None

@router.post("/api/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """Submit feedback for a chat session"""
    try:
        result = feedback_service.submit_feedback(
            session_id=feedback.session_id,
            rating=feedback.rating,
            category=feedback.category,
            comment=feedback.comment
        )
        return {"status": "success", "feedback_id": result["id"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/feedback/summary")
async def get_feedback_summary():
    """Get feedback summary for dashboard"""
    return feedback_service.get_feedback_summary()
