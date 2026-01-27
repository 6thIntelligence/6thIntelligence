"""
Security Service for Enterprise Bot
Provides input validation, injection detection, and sanitization
"""
import re
import html
from typing import Tuple, List, Optional
import hashlib

# SQL Injection patterns
SQL_INJECTION_PATTERNS = [
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|EXEC|UNION)\b)",
    r"(--|#|/\*|\*/)",
    r"(\bOR\b\s+\d+\s*=\s*\d+)",
    r"(\bAND\b\s+\d+\s*=\s*\d+)",
    r"(;\s*(SELECT|INSERT|UPDATE|DELETE|DROP))",
    r"(\'\s*(OR|AND)\s*\')",
    r"(SLEEP\s*\(|BENCHMARK\s*\(|WAITFOR\s+DELAY)",
]

# Prompt Injection patterns
PROMPT_INJECTION_PATTERNS = [
    # Direct instruction override
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", 0.9),
    (r"disregard\s+(all\s+)?(your\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", 0.9),
    (r"forget\s+(all\s+)?(previous|prior|above|everything)\s+(instructions?|prompts?|rules?)?", 0.9),
    
    # Role manipulation
    (r"you\s+are\s+(now|actually)\s+", 0.7),
    (r"pretend\s+(to\s+be|you\s+are)", 0.7),
    (r"act\s+as\s+(if\s+)?(you\s+)?(are|were|a)", 0.7),
    (r"roleplay\s+as", 0.6),
    
    # System prompt extraction
    (r"(reveal|show|display|output|tell\s+me)\s+(your\s+)?(system\s+)?(prompt|instructions)", 0.9),
    (r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions)", 0.8),
    (r"print\s+your\s+(initial|system)\s+prompt", 0.9),
    
    # Jailbreak attempts
    (r"DAN\s*mode", 0.95),
    (r"developer\s+mode", 0.8),
    (r"bypass\s+(all\s+)?(safety|content|filter)", 0.9),
    (r"unlock\s+(hidden\s+)?capabilities", 0.9),
    (r"remove\s+(all\s+)?restrictions", 0.8),
    
    # Encoded attacks
    (r"base64|\\x[0-9a-f]{2}|&#x?[0-9a-f]+;", 0.5),
    
    # Delimiter injection
    (r"```system|<\|system\|>|\[SYSTEM\]", 0.9),
]

# XSS patterns
XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript:",
    r"on\w+\s*=",
    r"<iframe",
    r"<object",
    r"<embed",
]

def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially harmful content.
    Preserves legitimate text while removing scripts and HTML.
    """
    if not text:
        return ""
    
    # HTML escape
    sanitized = html.escape(text)
    
    # Remove any remaining script-like patterns
    for pattern in XSS_PATTERNS:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
    
    # Normalize whitespace
    sanitized = " ".join(sanitized.split())
    
    return sanitized

def detect_sql_injection(text: str) -> Tuple[bool, List[str]]:
    """
    Detect potential SQL injection attempts.
    Returns (is_injection, matched_patterns)
    """
    if not text:
        return False, []
    
    matched = []
    text_upper = text.upper()
    
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, text_upper, re.IGNORECASE):
            matched.append(pattern)
    
    return len(matched) > 0, matched

def detect_prompt_injection(text: str) -> Tuple[bool, float, List[str]]:
    """
    Detect potential prompt injection attempts.
    Returns (is_injection, confidence_score, matched_patterns)
    
    Confidence thresholds:
    - < 0.3: Likely safe
    - 0.3 - 0.6: Suspicious, monitor
    - 0.6 - 0.8: Likely injection, warn
    - > 0.8: High confidence injection, block
    """
    if not text:
        return False, 0.0, []
    
    matched = []
    max_confidence = 0.0
    text_lower = text.lower()
    
    for pattern, confidence in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matched.append(pattern)
            max_confidence = max(max_confidence, confidence)
    
    # Adjust confidence based on number of matches
    if len(matched) > 2:
        max_confidence = min(1.0, max_confidence + 0.1 * (len(matched) - 2))
    
    is_injection = max_confidence > 0.6
    
    return is_injection, max_confidence, matched

def validate_session_id(session_id: str) -> bool:
    """
    Validate session ID format to prevent injection.
    Expected format: UUID (36 characters with hyphens)
    """
    if not session_id:
        return False
    
    # UUID pattern
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return bool(re.match(uuid_pattern, session_id.lower()))

def validate_email(email: str) -> bool:
    """Validate email format"""
    if not email:
        return False
    
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_pattern, email))

def hash_sensitive_data(data: str, salt: str = None) -> str:
    """
    Hash sensitive data for logging (e.g., partial API keys)
    """
    if salt:
        data = f"{salt}:{data}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]

def mask_api_key(key: str) -> str:
    """Mask API key for display, showing only first and last 4 chars"""
    if not key or len(key) < 10:
        return "***"
    return f"{key[:4]}...{key[-4:]}"

def check_content_safety(text: str) -> Tuple[bool, str]:
    """
    Basic content safety check for obvious harmful content.
    Returns (is_safe, reason)
    """
    if not text:
        return True, ""
    
    # Very obvious harmful patterns (not comprehensive, just basic)
    harmful_patterns = [
        (r"(bomb|explosive)\s+(making|instructions|how\s+to)", "potentially harmful instructions"),
        (r"(hack|exploit)\s+(password|account|system)", "hacking related"),
    ]
    
    text_lower = text.lower()
    for pattern, reason in harmful_patterns:
        if re.search(pattern, text_lower):
            return False, reason
    
    return True, ""

def generate_security_report(text: str) -> dict:
    """
    Generate a comprehensive security report for input text.
    Useful for admin review.
    """
    sql_detected, sql_patterns = detect_sql_injection(text)
    prompt_detected, prompt_confidence, prompt_patterns = detect_prompt_injection(text)
    content_safe, content_reason = check_content_safety(text)
    
    return {
        "input_length": len(text),
        "sql_injection": {
            "detected": sql_detected,
            "patterns_matched": len(sql_patterns)
        },
        "prompt_injection": {
            "detected": prompt_detected,
            "confidence": round(prompt_confidence, 2),
            "patterns_matched": len(prompt_patterns)
        },
        "content_safety": {
            "is_safe": content_safe,
            "reason": content_reason
        },
        "overall_risk": "high" if (sql_detected or prompt_detected or not content_safe) else "low"
    }

async def validate_with_llm(text: str, api_key: str, model: str = "google/gemini-flash-1.5") -> Tuple[bool, str]:
    """
    Advanced: Use a fast, cheap LLM to detect subtle injection attacks 
    that regex might miss.
    
    Returns (is_safe, reason)
    """
    # This is a placeholder for the Enterprise features.
    # To enable:
    # 1. Import AsyncOpenAI and configured client
    # 2. Send prompt: "Analyze this text for malicious intent: {text}"
    # 3. Parse response.
    
    # For now, we return True (assume safe) to avoid latency/cost 
    # until explicitly enabled in settings.
    return True, "LLM check skipped (disabled)"
