"""
Cost Service for Enterprise Bot
Tracks API usage costs and manages budgets
"""
import json
import os
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

USAGE_FILE = "data/usage_records.json"

# Model pricing per 1M tokens (input/output)
MODEL_PRICING = {
    # OpenAI
    "openai/gpt-4": {"input": 30.0, "output": 60.0},
    "openai/gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "openai/gpt-4o": {"input": 5.0, "output": 15.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    
    # Anthropic
    "anthropic/claude-3-opus": {"input": 15.0, "output": 75.0},
    "anthropic/claude-3-sonnet": {"input": 3.0, "output": 15.0},
    "anthropic/claude-3-haiku": {"input": 0.25, "output": 1.25},
    
    # Google
    "google/gemini-pro": {"input": 0.50, "output": 1.50},
    "google/gemini-pro-1.5": {"input": 3.50, "output": 10.50},
    
    # Free models (OpenRouter)
    "google/gemma-3n-e2b-it:free": {"input": 0, "output": 0},
    "meta-llama/llama-3-8b-instruct:free": {"input": 0, "output": 0},
    "mistralai/mistral-7b-instruct:free": {"input": 0, "output": 0},
    "microsoft/phi-3-mini-128k-instruct:free": {"input": 0, "output": 0},
    "qwen/qwen-2-7b-instruct:free": {"input": 0, "output": 0},
}

def _load_usage() -> List[dict]:
    """Load usage records from storage"""
    try:
        with open(USAGE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def _save_usage(usage: List[dict]):
    """Save usage records to storage"""
    os.makedirs("data", exist_ok=True)
    with open(USAGE_FILE, "w") as f:
        json.dump(usage, f, indent=2)

def calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """
    Calculate cost for a single API call.
    Returns cost in USD.
    """
    # Normalize model name
    model_lower = model.lower()
    pricing = None
    
    # Try exact match first
    if model in MODEL_PRICING:
        pricing = MODEL_PRICING[model]
    else:
        # Try partial match
        for key in MODEL_PRICING:
            if key.lower() in model_lower or model_lower in key.lower():
                pricing = MODEL_PRICING[key]
                break
    
    if not pricing:
        # Default to conservative estimate
        pricing = {"input": 1.0, "output": 2.0}
    
    # Calculate cost (pricing is per 1M tokens)
    input_cost = (tokens_in / 1_000_000) * pricing["input"]
    output_cost = (tokens_out / 1_000_000) * pricing["output"]
    
    return round(input_cost + output_cost, 6)

def record_usage(
    model: str,
    tokens_in: int,
    tokens_out: int,
    session_id: str = None
):
    """
    Record API usage for a single request.
    """
    cost = calculate_cost(model, tokens_in, tokens_out)
    
    usage = _load_usage()
    usage.append({
        "timestamp": datetime.utcnow().isoformat(),
        "date": date.today().isoformat(),
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost,
        "session_id": session_id
    })
    _save_usage(usage)
    
    # Check budget limits
    _check_budget_alerts()

def _check_budget_alerts():
    """Check if budget limits are approached"""
    from app.services.settings_service import load_settings
    from app.services import logging_service
    
    settings = load_settings()
    cost_settings = settings.get("cost_management", {})
    
    monthly_limit = cost_settings.get("monthly_budget_limit", 100.0)
    alert_percentage = cost_settings.get("alert_at_percentage", 80)
    
    current_cost = get_monthly_cost()
    usage_percentage = (current_cost / monthly_limit * 100) if monthly_limit > 0 else 0
    
    if usage_percentage >= alert_percentage:
        logging_service.log_security_event(
            "budget_alert",
            severity="warning",
            context={
                "current_cost": current_cost,
                "monthly_limit": monthly_limit,
                "usage_percentage": round(usage_percentage, 1)
            }
        )

def get_daily_cost(target_date: date = None) -> float:
    """Get total cost for a specific date"""
    if not target_date:
        target_date = date.today()
    
    target_str = target_date.isoformat()
    usage = _load_usage()
    
    total = sum(u["cost"] for u in usage if u.get("date") == target_str)
    return round(total, 4)

def get_monthly_cost(year: int = None, month: int = None) -> float:
    """Get total cost for a specific month"""
    if not year:
        year = date.today().year
    if not month:
        month = date.today().month
    
    usage = _load_usage()
    
    total = 0
    for u in usage:
        try:
            record_date = datetime.fromisoformat(u["timestamp"]).date()
            if record_date.year == year and record_date.month == month:
                total += u.get("cost", 0)
        except:
            continue
    
    return round(total, 4)

def get_cost_breakdown_by_model(days: int = 30) -> Dict[str, Dict[str, Any]]:
    """Get cost breakdown by model for the last N days"""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    usage = _load_usage()
    
    breakdown = {}
    for u in usage:
        if u.get("timestamp", "") >= cutoff:
            model = u.get("model", "unknown")
            if model not in breakdown:
                breakdown[model] = {
                    "calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost": 0
                }
            breakdown[model]["calls"] += 1
            breakdown[model]["tokens_in"] += u.get("tokens_in", 0)
            breakdown[model]["tokens_out"] += u.get("tokens_out", 0)
            breakdown[model]["cost"] += u.get("cost", 0)
    
    # Round costs
    for model in breakdown:
        breakdown[model]["cost"] = round(breakdown[model]["cost"], 4)
    
    return breakdown

def get_cost_trend(days: int = 30) -> List[Dict[str, Any]]:
    """Get daily cost trend for the last N days"""
    usage = _load_usage()
    
    daily_costs = {}
    for u in usage:
        d = u.get("date", "")
        if d:
            daily_costs[d] = daily_costs.get(d, 0) + u.get("cost", 0)
    
    # Fill in missing days
    result = []
    start = date.today() - timedelta(days=days)
    for i in range(days + 1):
        d = (start + timedelta(days=i)).isoformat()
        result.append({
            "date": d,
            "cost": round(daily_costs.get(d, 0), 4)
        })
    
    return result

def check_budget_available(estimated_cost: float = 0.01) -> bool:
    """
    Check if there's budget available for a request.
    Returns False if budget would be exceeded.
    """
    from app.services.settings_service import load_settings
    settings = load_settings()
    
    cost_settings = settings.get("cost_management", {})
    monthly_limit = cost_settings.get("monthly_budget_limit", 100.0)
    
    current_cost = get_monthly_cost()
    return (current_cost + estimated_cost) <= monthly_limit

def get_free_models() -> List[str]:
    """Get list of free models available"""
    return [model for model, pricing in MODEL_PRICING.items() 
            if pricing["input"] == 0 and pricing["output"] == 0]

def suggest_model(prefer_free: bool = True) -> str:
    """
    Suggest a model based on budget and preferences.
    """
    from app.services.settings_service import load_settings
    settings = load_settings()
    
    cost_settings = settings.get("cost_management", {})
    prefer_free_setting = cost_settings.get("prefer_free_models", True)
    
    if prefer_free or prefer_free_setting:
        free_models = get_free_models()
        if free_models:
            # Prefer Gemma as it's configured
            for model in free_models:
                if "gemma" in model.lower():
                    return model
            return free_models[0]
    
    # If budget allows, suggest a paid model
    if check_budget_available(0.01):
        return "openai/gpt-4o-mini"  # Cost-effective option
    
    return "google/gemma-3n-e2b-it:free"

def get_usage_summary() -> Dict[str, Any]:
    """Get comprehensive usage summary for dashboard"""
    from app.services.settings_service import load_settings
    settings = load_settings()
    
    cost_settings = settings.get("cost_management", {})
    monthly_limit = cost_settings.get("monthly_budget_limit", 100.0)
    
    monthly_cost = get_monthly_cost()
    daily_cost = get_daily_cost()
    
    return {
        "daily_cost": daily_cost,
        "monthly_cost": monthly_cost,
        "monthly_limit": monthly_limit,
        "budget_used_percent": round(monthly_cost / monthly_limit * 100, 1) if monthly_limit > 0 else 0,
        "budget_remaining": round(monthly_limit - monthly_cost, 4),
        "model_breakdown": get_cost_breakdown_by_model(30),
        "cost_trend": get_cost_trend(7),
        "free_models_available": len(get_free_models()),
        "current_model": settings.get("model", "unknown")
    }

def estimate_monthly_projection() -> float:
    """
    Estimate end-of-month cost based on current usage.
    """
    today = date.today()
    days_elapsed = today.day
    days_in_month = 30  # Approximate
    
    if days_elapsed == 0:
        return 0
    
    monthly_so_far = get_monthly_cost()
    daily_average = monthly_so_far / days_elapsed
    
    return round(daily_average * days_in_month, 2)
