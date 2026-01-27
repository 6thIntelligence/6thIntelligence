"""
Metrics Service for Enterprise Bot
Collects, stores, and aggregates performance and usage metrics
"""
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any
from sqlalchemy import func
from app.database import SessionLocal, Message, Session as ChatSession
import json

# In-memory metrics buffer for high-frequency operations
_metrics_buffer = []
_buffer_flush_interval = 60  # seconds
_last_flush = datetime.utcnow()

def record_response_time(session_id: str, duration_ms: float, model: str = None):
    """Record API response time"""
    _add_to_buffer({
        "type": "response_time",
        "session_id": session_id,
        "value": duration_ms,
        "model": model,
        "timestamp": datetime.utcnow().isoformat()
    })

def record_token_usage(session_id: str, tokens_in: int, tokens_out: int, model: str = None):
    """Record token usage for a request"""
    _add_to_buffer({
        "type": "token_usage",
        "session_id": session_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total": tokens_in + tokens_out,
        "model": model,
        "timestamp": datetime.utcnow().isoformat()
    })

def record_error(error_type: str, context: Dict[str, Any] = None):
    """Record error occurrence"""
    _add_to_buffer({
        "type": "error",
        "error_type": error_type,
        "context": context or {},
        "timestamp": datetime.utcnow().isoformat()
    })

def record_handover(session_id: str, reason: str, priority: str):
    """Record handover event"""
    _add_to_buffer({
        "type": "handover",
        "session_id": session_id,
        "reason": reason,
        "priority": priority,
        "timestamp": datetime.utcnow().isoformat()
    })

def record_feedback(session_id: str, rating: int, category: str = None):
    """Record user feedback"""
    _add_to_buffer({
        "type": "feedback",
        "session_id": session_id,
        "rating": rating,
        "category": category,
        "timestamp": datetime.utcnow().isoformat()
    })

def _add_to_buffer(metric: dict):
    """Add metric to buffer, flush if needed"""
    global _metrics_buffer, _last_flush
    _metrics_buffer.append(metric)
    
    # Check if we should flush
    if (datetime.utcnow() - _last_flush).seconds >= _buffer_flush_interval:
        _flush_buffer()

def _flush_buffer():
    """Flush metrics buffer to storage"""
    global _metrics_buffer, _last_flush
    
    if not _metrics_buffer:
        return
    
    # For now, write to a metrics log file
    # In production, this could go to a time-series DB like InfluxDB
    import os
    os.makedirs("logs", exist_ok=True)
    
    with open("logs/metrics.jsonl", "a") as f:
        for metric in _metrics_buffer:
            f.write(json.dumps(metric) + "\n")
    
    _metrics_buffer = []
    _last_flush = datetime.utcnow()

def get_daily_stats(start_date: date = None, end_date: date = None) -> Dict[str, Any]:
    """Get aggregated daily statistics"""
    db = SessionLocal()
    try:
        if not start_date:
            start_date = (datetime.utcnow() - timedelta(days=7)).date()
        if not end_date:
            end_date = datetime.utcnow().date()
        
        # Get session counts per day
        session_stats = db.query(
            func.date(ChatSession.created_at).label('date'),
            func.count(ChatSession.id).label('count')
        ).filter(
            func.date(ChatSession.created_at) >= start_date,
            func.date(ChatSession.created_at) <= end_date
        ).group_by(func.date(ChatSession.created_at)).all()
        
        # Get message counts per day
        message_stats = db.query(
            func.date(Message.timestamp).label('date'),
            func.count(Message.id).label('count'),
            func.sum(Message.tokens).label('tokens')
        ).filter(
            func.date(Message.timestamp) >= start_date,
            func.date(Message.timestamp) <= end_date
        ).group_by(func.date(Message.timestamp)).all()
        
        return {
            "sessions_by_day": {str(s.date): s.count for s in session_stats},
            "messages_by_day": {str(m.date): {"count": m.count, "tokens": m.tokens or 0} for m in message_stats},
            "date_range": {"start": str(start_date), "end": str(end_date)}
        }
    finally:
        db.close()

def get_hourly_breakdown(target_date: date = None) -> List[Dict[str, Any]]:
    """Get hourly activity breakdown for a specific date"""
    db = SessionLocal()
    try:
        if not target_date:
            target_date = datetime.utcnow().date()
        
        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)
        
        hourly_stats = db.query(
            func.strftime('%H', Message.timestamp).label('hour'),
            func.count(Message.id).label('count')
        ).filter(
            Message.timestamp >= start,
            Message.timestamp < end
        ).group_by(func.strftime('%H', Message.timestamp)).all()
        
        # Fill in all hours
        result = []
        hour_data = {int(h.hour): h.count for h in hourly_stats}
        for hour in range(24):
            result.append({
                "hour": f"{hour:02d}:00",
                "count": hour_data.get(hour, 0)
            })
        
        return result
    finally:
        db.close()

def get_model_usage_stats() -> Dict[str, Any]:
    """Get usage statistics by model (from metrics log)"""
    model_stats = {}
    
    try:
        with open("logs/metrics.jsonl", "r") as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())
                    if metric.get("type") == "token_usage":
                        model = metric.get("model", "unknown")
                        if model not in model_stats:
                            model_stats[model] = {"calls": 0, "tokens": 0}
                        model_stats[model]["calls"] += 1
                        model_stats[model]["tokens"] += metric.get("total", 0)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    
    return model_stats

def get_response_time_stats(hours: int = 24) -> Dict[str, Any]:
    """Get response time statistics for the last N hours"""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    response_times = []
    
    try:
        with open("logs/metrics.jsonl", "r") as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())
                    if metric.get("type") == "response_time":
                        if metric.get("timestamp", "") >= cutoff:
                            response_times.append(metric.get("value", 0))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    
    if not response_times:
        return {"avg": 0, "min": 0, "max": 0, "p95": 0, "count": 0}
    
    response_times.sort()
    count = len(response_times)
    p95_idx = int(count * 0.95)
    
    return {
        "avg": round(sum(response_times) / count, 2),
        "min": round(min(response_times), 2),
        "max": round(max(response_times), 2),
        "p95": round(response_times[p95_idx] if p95_idx < count else response_times[-1], 2),
        "count": count
    }

def get_error_rate(hours: int = 24) -> Dict[str, Any]:
    """Calculate error rate for the last N hours"""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    total_requests = 0
    error_count = 0
    errors_by_type = {}
    
    try:
        with open("logs/metrics.jsonl", "r") as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())
                    if metric.get("timestamp", "") >= cutoff:
                        if metric.get("type") == "response_time":
                            total_requests += 1
                        elif metric.get("type") == "error":
                            error_count += 1
                            error_type = metric.get("error_type", "unknown")
                            errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    
    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0
    
    return {
        "total_requests": total_requests,
        "error_count": error_count,
        "error_rate_percent": round(error_rate, 2),
        "errors_by_type": errors_by_type
    }

def get_conversation_quality_metrics() -> Dict[str, Any]:
    """Get conversation quality metrics"""
    db = SessionLocal()
    try:
        # Average messages per session
        session_msg_counts = db.query(
            Message.session_id,
            func.count(Message.id).label('count')
        ).group_by(Message.session_id).all()
        
        if session_msg_counts:
            avg_msgs = sum(s.count for s in session_msg_counts) / len(session_msg_counts)
        else:
            avg_msgs = 0
        
        # Total sessions and messages
        total_sessions = db.query(func.count(ChatSession.id)).scalar() or 0
        total_messages = db.query(func.count(Message.id)).scalar() or 0
        
        # User vs Assistant message ratio
        user_msgs = db.query(func.count(Message.id)).filter(Message.role == "user").scalar() or 0
        assistant_msgs = db.query(func.count(Message.id)).filter(Message.role == "assistant").scalar() or 0
        
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "avg_messages_per_session": round(avg_msgs, 1),
            "user_messages": user_msgs,
            "assistant_messages": assistant_msgs,
            "response_ratio": round(assistant_msgs / user_msgs, 2) if user_msgs > 0 else 0
        }
    finally:
        db.close()

def get_realtime_metrics() -> Dict[str, Any]:
    """Get real-time metrics for dashboard"""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)
        
        # Sessions in last hour
        sessions_last_hour = db.query(func.count(ChatSession.id)).filter(
            ChatSession.created_at >= last_hour
        ).scalar() or 0
        
        # Messages in last hour
        messages_last_hour = db.query(func.count(Message.id)).filter(
            Message.timestamp >= last_hour
        ).scalar() or 0
        
        # Active sessions (had activity in last hour)
        active_sessions = db.query(func.count(func.distinct(Message.session_id))).filter(
            Message.timestamp >= last_hour
        ).scalar() or 0
        
        # Response times from buffer
        response_stats = get_response_time_stats(1)
        
        return {
            "timestamp": now.isoformat(),
            "sessions_last_hour": sessions_last_hour,
            "messages_last_hour": messages_last_hour,
            "active_sessions": active_sessions,
            "avg_response_time_ms": response_stats["avg"],
            "p95_response_time_ms": response_stats["p95"]
        }
    finally:
        db.close()

def export_metrics(start_date: date, end_date: date, format: str = "json") -> str:
    """Export metrics data for external analysis"""
    stats = get_daily_stats(start_date, end_date)
    
    if format == "json":
        return json.dumps(stats, indent=2)
    elif format == "csv":
        lines = ["date,sessions,messages,tokens"]
        for d in sorted(set(list(stats["sessions_by_day"].keys()) + list(stats["messages_by_day"].keys()))):
            sessions = stats["sessions_by_day"].get(d, 0)
            msg_data = stats["messages_by_day"].get(d, {"count": 0, "tokens": 0})
            lines.append(f"{d},{sessions},{msg_data['count']},{msg_data['tokens']}")
        return "\n".join(lines)
    
    return json.dumps(stats)
