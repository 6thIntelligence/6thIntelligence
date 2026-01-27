"""
Feedback Service for Enterprise Bot
Handles user feedback collection, storage, and analysis
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

FEEDBACK_FILE = "data/feedback.json"

def _load_feedback() -> List[dict]:
    """Load feedback from storage"""
    try:
        with open(FEEDBACK_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def _save_feedback(feedback: List[dict]):
    """Save feedback to storage"""
    os.makedirs("data", exist_ok=True)
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(feedback, f, indent=2)

def _get_next_id() -> int:
    """Get next feedback ID"""
    feedback = _load_feedback()
    if not feedback:
        return 1
    return max(f["id"] for f in feedback) + 1

def submit_feedback(
    session_id: str,
    rating: int,
    category: str = None,
    comment: str = None,
    message_id: int = None
) -> dict:
    """
    Submit user feedback for a chat session.
    
    Args:
        session_id: Chat session ID
        rating: 1-5 star rating
        category: Optional category (response_quality, speed, accuracy, helpfulness)
        comment: Optional text comment
        message_id: Optional specific message ID this feedback is for
    
    Returns:
        The created feedback record
    """
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5")
    
    feedback_record = {
        "id": _get_next_id(),
        "session_id": session_id,
        "message_id": message_id,
        "rating": rating,
        "category": category,
        "comment": comment,
        "created_at": datetime.utcnow().isoformat()
    }
    
    feedback = _load_feedback()
    feedback.append(feedback_record)
    _save_feedback(feedback)
    
    # Log the feedback
    from app.services import logging_service, metrics_service
    logging_service.logger.info(f"Feedback received: Session {session_id[:8]}... rated {rating}/5")
    metrics_service.record_feedback(session_id, rating, category)
    
    return feedback_record

def get_session_feedback(session_id: str) -> List[dict]:
    """Get all feedback for a specific session"""
    feedback = _load_feedback()
    return [f for f in feedback if f["session_id"] == session_id]

def get_feedback_by_id(feedback_id: int) -> Optional[dict]:
    """Get specific feedback by ID"""
    feedback = _load_feedback()
    for f in feedback:
        if f["id"] == feedback_id:
            return f
    return None

def get_average_rating(days: int = None) -> float:
    """
    Calculate average rating.
    
    Args:
        days: Optional number of days to look back. None = all time.
    """
    feedback = _load_feedback()
    
    if days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        feedback = [f for f in feedback if f["created_at"] >= cutoff]
    
    if not feedback:
        return 0.0
    
    total_rating = sum(f["rating"] for f in feedback)
    return round(total_rating / len(feedback), 2)

def get_rating_distribution(days: int = None) -> Dict[int, int]:
    """
    Get distribution of ratings.
    Returns dict like {1: 5, 2: 10, 3: 25, 4: 40, 5: 20}
    """
    feedback = _load_feedback()
    
    if days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        feedback = [f for f in feedback if f["created_at"] >= cutoff]
    
    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for f in feedback:
        rating = f.get("rating", 3)
        distribution[rating] = distribution.get(rating, 0) + 1
    
    return distribution

def get_feedback_trends(interval: str = "daily", days: int = 30) -> List[Dict[str, Any]]:
    """
    Get feedback trends over time.
    
    Args:
        interval: "daily", "weekly", or "monthly"
        days: Number of days to look back
    """
    feedback = _load_feedback()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    feedback = [f for f in feedback if f["created_at"] >= cutoff]
    
    # Group by date
    daily_data = {}
    for f in feedback:
        date = f["created_at"][:10]  # YYYY-MM-DD
        if date not in daily_data:
            daily_data[date] = {"ratings": [], "count": 0}
        daily_data[date]["ratings"].append(f["rating"])
        daily_data[date]["count"] += 1
    
    # Calculate averages
    result = []
    for date in sorted(daily_data.keys()):
        data = daily_data[date]
        result.append({
            "date": date,
            "count": data["count"],
            "avg_rating": round(sum(data["ratings"]) / len(data["ratings"]), 2)
        })
    
    return result

def get_category_breakdown(days: int = None) -> Dict[str, Dict[str, Any]]:
    """
    Get feedback breakdown by category.
    """
    feedback = _load_feedback()
    
    if days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        feedback = [f for f in feedback if f["created_at"] >= cutoff]
    
    categories = {}
    for f in feedback:
        cat = f.get("category") or "general"
        if cat not in categories:
            categories[cat] = {"ratings": [], "count": 0}
        categories[cat]["ratings"].append(f["rating"])
        categories[cat]["count"] += 1
    
    result = {}
    for cat, data in categories.items():
        result[cat] = {
            "count": data["count"],
            "avg_rating": round(sum(data["ratings"]) / len(data["ratings"]), 2) if data["ratings"] else 0
        }
    
    return result

def get_low_rating_sessions(threshold: int = 2, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get sessions with low ratings for review.
    Useful for identifying issues and improving responses.
    
    Args:
        threshold: Rating threshold (return sessions with avg rating <= this)
        limit: Maximum number of sessions to return
    """
    feedback = _load_feedback()
    
    # Group by session
    session_ratings = {}
    for f in feedback:
        sid = f["session_id"]
        if sid not in session_ratings:
            session_ratings[sid] = {"ratings": [], "comments": [], "last_feedback": f["created_at"]}
        session_ratings[sid]["ratings"].append(f["rating"])
        if f.get("comment"):
            session_ratings[sid]["comments"].append(f["comment"])
        if f["created_at"] > session_ratings[sid]["last_feedback"]:
            session_ratings[sid]["last_feedback"] = f["created_at"]
    
    # Filter low ratings
    low_rated = []
    for sid, data in session_ratings.items():
        avg = sum(data["ratings"]) / len(data["ratings"])
        if avg <= threshold:
            low_rated.append({
                "session_id": sid,
                "avg_rating": round(avg, 2),
                "feedback_count": len(data["ratings"]),
                "comments": data["comments"],
                "last_feedback": data["last_feedback"]
            })
    
    # Sort by avg rating (lowest first)
    low_rated.sort(key=lambda x: x["avg_rating"])
    
    return low_rated[:limit]

def get_recent_comments(limit: int = 20, min_rating: int = None, max_rating: int = None) -> List[dict]:
    """
    Get recent feedback with comments.
    Useful for understanding user sentiment.
    """
    feedback = _load_feedback()
    
    # Filter to only those with comments
    with_comments = [f for f in feedback if f.get("comment")]
    
    # Apply rating filters
    if min_rating is not None:
        with_comments = [f for f in with_comments if f["rating"] >= min_rating]
    if max_rating is not None:
        with_comments = [f for f in with_comments if f["rating"] <= max_rating]
    
    # Sort by date (newest first) and limit
    with_comments.sort(key=lambda x: x["created_at"], reverse=True)
    
    return with_comments[:limit]

def get_feedback_summary() -> Dict[str, Any]:
    """Get comprehensive feedback summary for dashboard"""
    feedback = _load_feedback()
    
    if not feedback:
        return {
            "total_feedback": 0,
            "avg_rating": 0,
            "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "category_breakdown": {},
            "satisfaction_rate": 0,
            "recent_trend": "neutral"
        }
    
    # Calculate satisfaction rate (4 or 5 stars)
    satisfied = sum(1 for f in feedback if f["rating"] >= 4)
    satisfaction_rate = round(satisfied / len(feedback) * 100, 1)
    
    # Determine recent trend
    recent = [f for f in feedback if f["created_at"] >= (datetime.utcnow() - timedelta(days=7)).isoformat()]
    older = [f for f in feedback if f["created_at"] < (datetime.utcnow() - timedelta(days=7)).isoformat()]
    
    if recent and older:
        recent_avg = sum(f["rating"] for f in recent) / len(recent)
        older_avg = sum(f["rating"] for f in older) / len(older)
        if recent_avg > older_avg + 0.2:
            trend = "improving"
        elif recent_avg < older_avg - 0.2:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"
    
    return {
        "total_feedback": len(feedback),
        "avg_rating": get_average_rating(),
        "rating_distribution": get_rating_distribution(),
        "category_breakdown": get_category_breakdown(),
        "satisfaction_rate": satisfaction_rate,
        "recent_trend": trend,
        "feedback_last_7_days": len(recent),
        "low_rating_count": sum(1 for f in feedback if f["rating"] <= 2)
    }
