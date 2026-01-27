"""
Handover Router for Enterprise Bot
Manages escalation queue and human handover
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from app.services import handover_service
from app.routers.admin import get_current_user

router = APIRouter(prefix="/api/handovers", tags=["Handovers"])

class AssignRequest(BaseModel):
    staff_email: str

class ResolveRequest(BaseModel):
    notes: Optional[str] = None

class CreateHandoverRequest(BaseModel):
    session_id: str
    reason: str
    priority: str = "normal"
    notes: Optional[str] = None

@router.get("")
async def list_handovers(
    status: Optional[str] = Query(None, description="Filter by status: pending, assigned, resolved"),
    priority: Optional[str] = Query(None, description="Filter by priority: normal, high, urgent"),
    limit: int = Query(50, le=100),
    user: str = Depends(get_current_user)
):
    """Get all handovers with optional filters"""
    handovers = handover_service._load_handovers()
    
    # Apply filters
    if status:
        handovers = [h for h in handovers if h.get("status") == status]
    if priority:
        handovers = [h for h in handovers if h.get("priority") == priority]
    
    # Sort by priority (urgent first) then by created_at
    priority_order = {"urgent": 0, "high": 1, "normal": 2}
    handovers.sort(key=lambda h: (
        priority_order.get(h.get("priority", "normal"), 2),
        h.get("created_at", "")
    ))
    
    return {
        "handovers": handovers[:limit],
        "total": len(handovers)
    }

@router.get("/pending")
async def get_pending_handovers(user: str = Depends(get_current_user)):
    """Get only pending handovers"""
    pending = handover_service.get_pending_handovers()
    
    # Sort by priority
    priority_order = {"urgent": 0, "high": 1, "normal": 2}
    pending.sort(key=lambda h: priority_order.get(h.get("priority", "normal"), 2))
    
    return {"handovers": pending, "count": len(pending)}

@router.get("/stats")
async def get_handover_stats(user: str = Depends(get_current_user)):
    """Get handover statistics"""
    return handover_service.get_handover_stats()

@router.get("/{handover_id}")
async def get_handover_detail(
    handover_id: int,
    user: str = Depends(get_current_user)
):
    """Get details of a specific handover"""
    handover = handover_service.get_handover(handover_id)
    
    if not handover:
        raise HTTPException(status_code=404, detail="Handover not found")
    
    # Get session messages for context
    from app.services.db_service import get_db_service
    db = get_db_service()
    messages = db.get_messages(handover["session_id"], limit=50)
    
    return {
        "handover": handover,
        "conversation": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
            for m in messages
        ]
    }

@router.post("")
async def create_handover(
    request: CreateHandoverRequest,
    user: str = Depends(get_current_user)
):
    """Manually create a handover"""
    handover = handover_service.create_handover(
        session_id=request.session_id,
        reason=request.reason,
        priority=request.priority,
        notes=request.notes
    )
    
    return {"status": "created", "handover": handover}

@router.post("/{handover_id}/assign")
async def assign_handover(
    handover_id: int,
    request: AssignRequest,
    user: str = Depends(get_current_user)
):
    """Assign a handover to a staff member"""
    handover = handover_service.assign_handover(handover_id, request.staff_email)
    
    if not handover:
        raise HTTPException(status_code=404, detail="Handover not found")
    
    return {"status": "assigned", "handover": handover}

@router.post("/{handover_id}/resolve")
async def resolve_handover(
    handover_id: int,
    request: ResolveRequest,
    user: str = Depends(get_current_user)
):
    """Mark a handover as resolved"""
    handover = handover_service.resolve_handover(handover_id, request.notes)
    
    if not handover:
        raise HTTPException(status_code=404, detail="Handover not found")
    
    return {"status": "resolved", "handover": handover}

@router.post("/{handover_id}/notify")
async def send_notification(
    handover_id: int,
    channels: List[str] = Query(default=["email"]),
    user: str = Depends(get_current_user)
):
    """Send notification for a handover"""
    handover = handover_service.get_handover(handover_id)
    
    if not handover:
        raise HTTPException(status_code=404, detail="Handover not found")
    
    results = await handover_service.send_notification(handover, channels)
    
    return {"status": "notification_sent", "results": results}

@router.post("/detect")
async def detect_escalation(
    message: str,
    session_history: Optional[List[str]] = None,
    user: str = Depends(get_current_user)
):
    """
    Detect if a message needs escalation.
    Useful for testing escalation detection.
    """
    needs_handover, reason, priority = handover_service.detect_escalation_need(
        message, 
        session_history or []
    )
    
    return {
        "needs_handover": needs_handover,
        "reason": reason,
        "priority": priority,
        "sentiment": handover_service.analyze_sentiment(message)
    }
