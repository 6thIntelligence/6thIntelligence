from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from app.services import settings_service, openrouter_service, auth_service
from app import database
from sqlalchemy.orm import Session

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

class ConfigUpdate(BaseModel):
    openrouter_api_key: Optional[str] = None
    model: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    system_persona: Optional[str] = None
    response_delay_min: Optional[float] = None
    response_delay_max: Optional[float] = None
    db_connection: Optional[str] = None
    crm_api_key: Optional[str] = None
    persona_type: Optional[str] = None

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token or not token.startswith("Bearer "):
        # Use HTMLResponse for redirect if not authenticated
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    token_str = token.split(" ")[1]
    payload = auth_service.decode_access_token(token_str)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload["sub"]

@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user: str = Depends(get_current_user)):
    settings = settings_service.load_settings()
    # Mask key for display
    pk = settings.get("openrouter_api_key", "")
    masked_key = f"{pk[:4]}...{pk[-4:]}" if len(pk) > 10 else ""
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "settings": settings,
        "masked_key": masked_key,
        "user_email": user
    })

@router.get("/api/admin/config")
async def get_config(user: str = Depends(get_current_user)):
    return settings_service.load_settings()

@router.post("/api/admin/config")
async def update_config(config: ConfigUpdate, user: str = Depends(get_current_user)):
    # Only update provided fields
    data = config.model_dump(exclude_unset=True)
    settings_service.save_settings(data)
    return {"status": "success", "settings": settings_service.load_settings()}

@router.get("/api/admin/models")
async def get_models(user: str = Depends(get_current_user)):
    models = await openrouter_service.fetch_available_models()
    return {"models": models}

@router.get("/api/admin/kb")
async def get_kb_docs(db: Session = Depends(database.get_db), user: str = Depends(get_current_user)):
    docs = db.query(database.KnowledgeDoc).all()
    return {"docs": [{"id": d.id, "filename": d.filename, "date": d.upload_date.isoformat()} for d in docs]}

@router.delete("/api/admin/kb/{doc_id}")
async def delete_kb_doc(doc_id: int, db: Session = Depends(database.get_db), user: str = Depends(get_current_user)):
    doc = db.query(database.KnowledgeDoc).filter(database.KnowledgeDoc.id == doc_id).first()
    if doc:
        # Delete from ChromaDB
        from app.services import knowledge_service
        knowledge_service.delete_document(str(doc_id))
        
        db.delete(doc)
        db.commit()
    return {"status": "success"}

@router.get("/api/admin/handovers")
async def get_handovers(db: Session = Depends(database.get_db), user: str = Depends(get_current_user)):
    sessions = db.query(database.Session).all()
    results = []
    for s in sessions:
        msgs = db.query(database.Message).filter(database.Message.session_id == s.id).all()
        is_handover = any("human" in m.content.lower() or "agent" in m.content.lower() for m in msgs if m.role == "user")
        if is_handover:
            results.append({"id": s.id, "name": s.name, "created_at": s.created_at.isoformat()})
    return {"handovers": results}

@router.get("/api/admin/logs")
async def get_all_logs(db: Session = Depends(database.get_db), user: str = Depends(get_current_user)):
    sessions = db.query(database.Session).order_by(database.Session.created_at.desc()).all()
    results = []
    for s in sessions:
        msg_count = db.query(database.Message).filter(database.Message.session_id == s.id).count()
        results.append({
            "id": s.id,
            "name": s.name,
            "created_at": s.created_at.isoformat(),
            "msg_count": msg_count
        })
    return {"logs": results}

@router.get("/api/admin/logs/{session_id}")
async def get_session_detail(session_id: str, db: Session = Depends(database.get_db), user: str = Depends(get_current_user)):
    msgs = db.query(database.Message).filter(database.Message.session_id == session_id).order_by(database.Message.timestamp).all()
    return {"messages": [{"role": m.role, "content": m.content, "time": m.timestamp.isoformat()} for m in msgs]}

@router.get("/api/admin/stats")
async def get_dashboard_stats(db: Session = Depends(database.get_db), user: str = Depends(get_current_user)):
    from sqlalchemy import func
    from datetime import datetime, timedelta
    from app.services import metrics_service, cost_service, feedback_service, handover_service
    
    # 1. Token Usage (Last 7 days)
    token_stats = []
    # Try database first
    db_tokens_total = 0
    for i in range(6, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).date()
        tokens = db.query(func.sum(database.Message.tokens)).filter(func.date(database.Message.timestamp) == day).scalar() or 0
        db_tokens_total += tokens
        token_stats.append({"date": day.strftime("%b %d"), "day_obj": day, "count": tokens})
    
    # If DB is empty, use metrics service (which reads from logs/metrics.jsonl)
    if db_tokens_total == 0:
        daily_metrics = metrics_service.get_daily_stats().get("messages_by_day", {})
        for stat in token_stats:
            day_str = str(stat["day_obj"])
            if day_str in daily_metrics:
                stat["count"] = daily_metrics[day_str].get("tokens", 0)
    
    # Clean up for response
    for s in token_stats: s.pop("day_obj", None)
    
    # 2. Activity Heatmap (Last 365 days)
    heatmap_query = db.query(func.date(database.Session.created_at).label('date'), func.count(database.Session.id).label('count')) \
                      .filter(database.Session.created_at >= datetime.utcnow() - timedelta(days=365)) \
                      .group_by(func.date(database.Session.created_at)).all()
    
    heatmap_data = {str(row.date): row.count for row in heatmap_query}
    
    # 3. Real-time metrics
    realtime = metrics_service.get_realtime_metrics()
    
    # 4. Cost summary
    cost_summary = cost_service.get_usage_summary()
    
    # 5. Feedback summary
    feedback_summary = feedback_service.get_feedback_summary()
    
    # 6. Handover stats
    handover_stats = handover_service.get_handover_stats()
    
    return {
        "token_stats": token_stats,
        "heatmap": heatmap_data,
        "realtime": realtime,
        "cost": cost_summary,
        "feedback": feedback_summary,
        "handovers": handover_stats
    }

@router.get("/api/admin/metrics")
async def get_detailed_metrics(user: str = Depends(get_current_user)):
    """Get detailed performance metrics"""
    from app.services import metrics_service
    from datetime import date, timedelta
    
    return {
        "daily_stats": metrics_service.get_daily_stats(),
        "hourly_breakdown": metrics_service.get_hourly_breakdown(),
        "response_times": metrics_service.get_response_time_stats(24),
        "error_rate": metrics_service.get_error_rate(24),
        "conversation_quality": metrics_service.get_conversation_quality_metrics(),
        "model_usage": metrics_service.get_model_usage_stats()
    }

@router.get("/api/admin/metrics/realtime")
async def get_realtime_metrics(user: str = Depends(get_current_user)):
    """Get real-time metrics for dashboard refresh"""
    from app.services import metrics_service
    return metrics_service.get_realtime_metrics()

@router.get("/api/admin/costs")
async def get_cost_details(user: str = Depends(get_current_user)):
    """Get detailed cost breakdown"""
    from app.services import cost_service
    
    return {
        "summary": cost_service.get_usage_summary(),
        "trend": cost_service.get_cost_trend(30),
        "model_breakdown": cost_service.get_cost_breakdown_by_model(30),
        "monthly_projection": cost_service.estimate_monthly_projection(),
        "free_models": cost_service.get_free_models()
    }

@router.get("/api/admin/system/logs")
async def get_system_logs(
    limit: int = 100,
    level: str = None,
    category: str = None,
    user: str = Depends(get_current_user)
):
    """Get recent system logs"""
    from app.services import logging_service
    return {
        "logs": logging_service.get_recent_logs(limit, level, category)
    }

@router.get("/api/admin/security/events")
async def get_security_events(user: str = Depends(get_current_user)):
    """Get recent security events"""
    from app.services import logging_service
    return {
        "events": logging_service.get_recent_logs(50, category="security")
    }

@router.get("/api/admin/health")
async def health_check(user: str = Depends(get_current_user)):
    """Check system health"""
    from app.services.db_service import get_db_service
    from app.services import cache_service
    
    db_service = get_db_service()
    
    return {
        "status": "healthy",
        "database": "connected" if db_service.health_check() else "error",
        "cache_stats": cache_service.get_cache_stats(),
        "db_stats": db_service.get_stats()
    }
