"""
Centralized Logging Service for Enterprise Bot
Provides structured logging with database and file handlers
"""
import logging
import json
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler

# Create logs directory
os.makedirs("logs", exist_ok=True)

# Configure JSON formatter
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_entry["data"] = record.extra_data
            
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

# Setup main logger
def setup_logger(name: str = "enterprise_bot", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
        
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Console handler with standard format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler with JSON format
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    # Error file handler
    error_handler = RotatingFileHandler(
        "logs/error.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    logger.addHandler(error_handler)
    
    return logger

# Global logger instance
logger = setup_logger()

def generate_request_id() -> str:
    """Generate unique request ID for tracking"""
    return str(uuid.uuid4())[:8]

def log_request(
    request_id: str,
    endpoint: str,
    method: str,
    user_agent: str = None,
    ip_address: str = None,
    extra: Dict[str, Any] = None
):
    """Log incoming request"""
    data = {
        "request_id": request_id,
        "endpoint": endpoint,
        "method": method,
        "user_agent": user_agent,
        "ip_address": ip_address,
        "category": "request"
    }
    if extra:
        data.update(extra)
    
    record = logger.makeRecord(
        logger.name, logging.INFO, "", 0,
        f"Request: {method} {endpoint}", (), None
    )
    record.extra_data = data
    logger.handle(record)

def log_response(
    request_id: str,
    status_code: int,
    response_time_ms: float,
    extra: Dict[str, Any] = None
):
    """Log outgoing response"""
    data = {
        "request_id": request_id,
        "status_code": status_code,
        "response_time_ms": round(response_time_ms, 2),
        "category": "response"
    }
    if extra:
        data.update(extra)
    
    level = logging.INFO if status_code < 400 else logging.WARNING
    record = logger.makeRecord(
        logger.name, level, "", 0,
        f"Response: {status_code} in {response_time_ms:.2f}ms", (), None
    )
    record.extra_data = data
    logger.handle(record)

def log_error(
    error_type: str,
    message: str,
    stack_trace: str = None,
    context: Dict[str, Any] = None,
    request_id: str = None
):
    """Log error with context"""
    data = {
        "error_type": error_type,
        "category": "error",
        "request_id": request_id
    }
    if context:
        data.update(context)
    if stack_trace:
        data["stack_trace"] = stack_trace
    
    record = logger.makeRecord(
        logger.name, logging.ERROR, "", 0,
        f"Error [{error_type}]: {message}", (), None
    )
    record.extra_data = data
    logger.handle(record)

def log_chat_interaction(
    session_id: str,
    user_message: str,
    ai_response: str,
    tokens_used: int = 0,
    response_time_ms: float = 0,
    model: str = None
):
    """Log chat interaction for analytics"""
    data = {
        "session_id": session_id,
        "user_message_length": len(user_message),
        "ai_response_length": len(ai_response),
        "tokens_used": tokens_used,
        "response_time_ms": round(response_time_ms, 2),
        "model": model,
        "category": "chat"
    }
    
    record = logger.makeRecord(
        logger.name, logging.INFO, "", 0,
        f"Chat: Session {session_id[:8]}... - {tokens_used} tokens", (), None
    )
    record.extra_data = data
    logger.handle(record)

def log_security_event(
    event_type: str,
    severity: str = "warning",
    context: Dict[str, Any] = None
):
    """Log security-related events"""
    data = {
        "event_type": event_type,
        "severity": severity,
        "category": "security"
    }
    if context:
        data.update(context)
    
    level = logging.WARNING if severity != "critical" else logging.CRITICAL
    record = logger.makeRecord(
        logger.name, level, "", 0,
        f"Security Event [{event_type}]: {severity}", (), None
    )
    record.extra_data = data
    logger.handle(record)

def log_handover_event(
    session_id: str,
    handover_id: int,
    action: str,
    details: Dict[str, Any] = None
):
    """Log handover/escalation events"""
    data = {
        "session_id": session_id,
        "handover_id": handover_id,
        "action": action,
        "category": "handover"
    }
    if details:
        data.update(details)
    
    record = logger.makeRecord(
        logger.name, logging.INFO, "", 0,
        f"Handover: {action} for session {session_id[:8]}...", (), None
    )
    record.extra_data = data
    logger.handle(record)

def log_metric(
    metric_name: str,
    value: float,
    tags: Dict[str, str] = None
):
    """Log metrics for monitoring"""
    data = {
        "metric_name": metric_name,
        "value": value,
        "tags": tags or {},
        "category": "metric"
    }
    
    record = logger.makeRecord(
        logger.name, logging.DEBUG, "", 0,
        f"Metric: {metric_name}={value}", (), None
    )
    record.extra_data = data
    logger.handle(record)

def get_recent_logs(limit: int = 100, level: str = None, category: str = None) -> list:
    """
    Read recent logs from file for admin dashboard.
    Returns parsed log entries.
    """
    logs = []
    try:
        with open("logs/app.log", "r") as f:
            lines = f.readlines()[-limit:]
            for line in lines:
                try:
                    entry = json.loads(line.strip())
                    if level and entry.get("level") != level:
                        continue
                    if category and entry.get("data", {}).get("category") != category:
                        continue
                    logs.append(entry)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return logs
