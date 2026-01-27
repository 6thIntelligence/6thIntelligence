"""
Handover Service for Enterprise Bot
Manages escalation detection, handover queue, and notifications
"""
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional
import httpx
import json
from app.database import SessionLocal

# Escalation keywords with priority weights
ESCALATION_KEYWORDS = {
    "urgent": ("urgent", 3),
    "emergency": ("urgent", 3),
    "critical": ("urgent", 3),
    "human": ("high", 2),
    "agent": ("high", 2),
    "support": ("normal", 1),
    "manager": ("high", 2),
    "supervisor": ("high", 2),
    "speak to": ("high", 2),
    "talk to": ("high", 2),
    "help me": ("normal", 1),
    "not working": ("normal", 1),
    "frustrated": ("high", 2),
    "angry": ("high", 2),
    "complaint": ("high", 2),
    "escalate": ("high", 2),
    "real person": ("high", 2),
}

# Negative sentiment indicators
NEGATIVE_INDICATORS = [
    "terrible", "awful", "horrible", "worst", "useless",
    "doesn't work", "not helpful", "waste of time",
    "disappointed", "frustrating", "ridiculous",
    "unacceptable", "pathetic", "incompetent"
]

def analyze_sentiment(message: str) -> float:
    """
    Basic sentiment analysis.
    Returns score from -1 (negative) to 1 (positive).
    """
    if not message:
        return 0.0
    
    message_lower = message.lower()
    score = 0.0
    
    # Check negative indicators
    for indicator in NEGATIVE_INDICATORS:
        if indicator in message_lower:
            score -= 0.3
    
    # Check escalation keywords
    for keyword, (priority, weight) in ESCALATION_KEYWORDS.items():
        if keyword in message_lower:
            if priority in ["urgent", "high"]:
                score -= 0.2
    
    # Check positive indicators
    positive_words = ["thanks", "great", "helpful", "appreciate", "good", "excellent"]
    for word in positive_words:
        if word in message_lower:
            score += 0.2
    
    return max(-1.0, min(1.0, score))

def detect_escalation_need(
    message: str, 
    session_history: List[str] = None
) -> Tuple[bool, str, str]:
    """
    Detect if conversation needs human handover.
    Returns (needs_handover, reason, priority)
    
    Reasons:
    - keyword_detected: User explicitly asked for human/support
    - sentiment_negative: User shows frustration
    - repeated_issues: Multiple attempts without resolution
    """
    if not message:
        return False, "", "normal"
    
    message_lower = message.lower()
    reasons = []
    max_priority = "normal"
    priority_order = {"normal": 1, "high": 2, "urgent": 3}
    
    # Check for escalation keywords
    for keyword, (priority, weight) in ESCALATION_KEYWORDS.items():
        if keyword in message_lower:
            reasons.append(f"keyword:{keyword}")
            if priority_order.get(priority, 1) > priority_order.get(max_priority, 1):
                max_priority = priority
    
    # Check sentiment
    sentiment = analyze_sentiment(message)
    if sentiment < -0.5:
        reasons.append("negative_sentiment")
        if max_priority == "normal":
            max_priority = "high"
    
    # Check session history for patterns
    if session_history and len(session_history) > 4:
        # Look for repeated similar messages (user might be stuck)
        recent_msgs = [m.lower() for m in session_history[-4:]]
        similarity_count = sum(1 for m in recent_msgs if any(
            word in m for word in ["help", "not working", "again", "still"]
        ))
        if similarity_count >= 2:
            reasons.append("repeated_issues")
            if max_priority == "normal":
                max_priority = "high"
    
    needs_handover = len(reasons) > 0
    reason = ", ".join(reasons) if reasons else ""
    
    return needs_handover, reason, max_priority

def create_handover(
    session_id: str, 
    reason: str, 
    priority: str = "normal",
    notes: str = None
) -> dict:
    """
    Create a handover record in the database.
    Returns the created handover data.
    """
    from app.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Check if Handover model exists, if not create record in a simple way
        # For now, we'll store in a JSON file until DB migration
        import os
        os.makedirs("data", exist_ok=True)
        
        handover = {
            "id": _get_next_handover_id(),
            "session_id": session_id,
            "reason": reason,
            "priority": priority,
            "status": "pending",
            "assigned_to": None,
            "created_at": datetime.utcnow().isoformat(),
            "resolved_at": None,
            "notes": notes
        }
        
        # Append to handovers file
        handovers = _load_handovers()
        handovers.append(handover)
        _save_handovers(handovers)
        
        # Log the event
        from app.services import logging_service
        logging_service.log_handover_event(
            session_id=session_id,
            handover_id=handover["id"],
            action="created",
            details={"reason": reason, "priority": priority}
        )
        
        return handover
    finally:
        db.close()

def _get_next_handover_id() -> int:
    """Get next handover ID"""
    handovers = _load_handovers()
    if not handovers:
        return 1
    return max(h["id"] for h in handovers) + 1

def _load_handovers() -> List[dict]:
    """Load handovers from JSON file"""
    try:
        with open("data/handovers.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def _save_handovers(handovers: List[dict]):
    """Save handovers to JSON file"""
    import os
    os.makedirs("data", exist_ok=True)
    with open("data/handovers.json", "w") as f:
        json.dump(handovers, f, indent=2)

def get_pending_handovers() -> List[dict]:
    """Get all pending handovers"""
    handovers = _load_handovers()
    return [h for h in handovers if h["status"] == "pending"]

def get_handover(handover_id: int) -> Optional[dict]:
    """Get a specific handover by ID"""
    handovers = _load_handovers()
    for h in handovers:
        if h["id"] == handover_id:
            return h
    return None

def assign_handover(handover_id: int, staff_email: str) -> Optional[dict]:
    """Assign a handover to a staff member"""
    handovers = _load_handovers()
    for h in handovers:
        if h["id"] == handover_id:
            h["status"] = "assigned"
            h["assigned_to"] = staff_email
            _save_handovers(handovers)
            
            from app.services import logging_service
            logging_service.log_handover_event(
                session_id=h["session_id"],
                handover_id=handover_id,
                action="assigned",
                details={"assigned_to": staff_email}
            )
            return h
    return None

def resolve_handover(handover_id: int, notes: str = None) -> Optional[dict]:
    """Mark a handover as resolved"""
    handovers = _load_handovers()
    for h in handovers:
        if h["id"] == handover_id:
            h["status"] = "resolved"
            h["resolved_at"] = datetime.utcnow().isoformat()
            if notes:
                h["notes"] = (h.get("notes") or "") + f"\nResolution: {notes}"
            _save_handovers(handovers)
            
            from app.services import logging_service
            logging_service.log_handover_event(
                session_id=h["session_id"],
                handover_id=handover_id,
                action="resolved",
                details={"notes": notes}
            )
            return h
    return None

async def send_notification(handover: dict, channels: List[str] = None):
    """
    Send notifications through specified channels.
    Channels: email, webhook
    """
    if not channels:
        channels = ["email"]
    
    from app.services.settings_service import load_settings
    settings = load_settings()
    
    results = {}
    
    for channel in channels:
        try:
            if channel == "email":
                email = settings.get("handover", {}).get("notification_email")
                if email:
                    await send_email_alert(handover, email)
                    results["email"] = "sent"
                else:
                    results["email"] = "no_email_configured"
                    
            elif channel == "webhook":
                webhook_url = settings.get("handover", {}).get("webhook_url")
                if webhook_url:
                    await send_webhook(handover, webhook_url)
                    results["webhook"] = "sent"
                else:
                    results["webhook"] = "no_webhook_configured"
                    
        except Exception as e:
            results[channel] = f"error: {str(e)}"
            from app.services import logging_service
            logging_service.log_error(
                error_type="notification_failed",
                message=str(e),
                context={"channel": channel, "handover_id": handover["id"]}
            )
    
    return results

async def send_email_alert(handover: dict, recipient: str):
    """Send email notification for handover"""
    from app.services.settings_service import load_settings
    settings = load_settings()
    
    # Get SMTP settings (would need to be configured)
    smtp_server = settings.get("smtp", {}).get("server", "smtp.gmail.com")
    smtp_port = settings.get("smtp", {}).get("port", 587)
    smtp_user = settings.get("smtp", {}).get("user", "")
    smtp_password = settings.get("smtp", {}).get("password", "")
    
    if not smtp_user or not smtp_password:
        # Log that email is not configured
        from app.services import logging_service
        logging_service.log_error(
            error_type="email_not_configured",
            message="SMTP credentials not configured",
            context={"handover_id": handover["id"]}
        )
        return
    
    # Create email
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg["Subject"] = f"[{handover['priority'].upper()}] New Handover Request - Session {handover['session_id'][:8]}"
    
    body = f"""
New handover request requires your attention.

Session ID: {handover['session_id']}
Priority: {handover['priority'].upper()}
Reason: {handover['reason']}
Created: {handover['created_at']}

Please log in to the admin dashboard to handle this request.
    """
    
    msg.attach(MIMEText(body, "plain"))
    
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient, msg.as_string())
        server.quit()
    except Exception as e:
        raise Exception(f"Failed to send email: {str(e)}")

async def send_webhook(handover: dict, url: str):
    """Send webhook notification for handover"""
    payload = {
        "event": "handover_created",
        "handover_id": handover["id"],
        "session_id": handover["session_id"],
        "priority": handover["priority"],
        "reason": handover["reason"],
        "status": handover["status"],
        "created_at": handover["created_at"],
        "timestamp": datetime.utcnow().isoformat()
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        if response.status_code >= 400:
            raise Exception(f"Webhook returned status {response.status_code}")

def get_handover_stats() -> Dict[str, Any]:
    """Get handover statistics"""
    handovers = _load_handovers()
    
    if not handovers:
        return {
            "total": 0,
            "pending": 0,
            "assigned": 0,
            "resolved": 0,
            "by_priority": {},
            "avg_resolution_time_hours": 0
        }
    
    status_counts = {"pending": 0, "assigned": 0, "resolved": 0}
    priority_counts = {"normal": 0, "high": 0, "urgent": 0}
    resolution_times = []
    
    for h in handovers:
        status_counts[h.get("status", "pending")] += 1
        priority_counts[h.get("priority", "normal")] += 1
        
        if h.get("resolved_at") and h.get("created_at"):
            try:
                created = datetime.fromisoformat(h["created_at"])
                resolved = datetime.fromisoformat(h["resolved_at"])
                hours = (resolved - created).total_seconds() / 3600
                resolution_times.append(hours)
            except:
                pass
    
    avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0
    
    return {
        "total": len(handovers),
        "pending": status_counts["pending"],
        "assigned": status_counts["assigned"],
        "resolved": status_counts["resolved"],
        "by_priority": priority_counts,
        "avg_resolution_time_hours": round(avg_resolution, 2)
    }
