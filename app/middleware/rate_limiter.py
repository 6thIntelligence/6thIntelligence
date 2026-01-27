"""
Rate Limiting Middleware for FastAPI
Protects against abuse and DDoS attacks
"""
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Tuple
import asyncio

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60, chat_requests_per_minute: int = 10):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.chat_requests_per_minute = chat_requests_per_minute
        self.request_counts: Dict[str, list] = defaultdict(list)
        self.chat_counts: Dict[str, list] = defaultdict(list)
        self.blocked_ips: Dict[str, float] = {}  # IP -> unblock time
        self.whitelist = set()  # Admin IPs to whitelist
        self._cleanup_lock = asyncio.Lock()
        
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP, considering proxy headers"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _cleanup_old_requests(self, timestamps: list, window_seconds: int = 60):
        """Remove timestamps older than the window"""
        current_time = time.time()
        cutoff = current_time - window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
    
    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Skip rate limiting for whitelisted IPs
        if client_ip in self.whitelist:
            return await call_next(request)
        
        # Check if IP is blocked
        if client_ip in self.blocked_ips:
            if current_time < self.blocked_ips[client_ip]:
                remaining = int(self.blocked_ips[client_ip] - current_time)
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many requests. Try again in {remaining} seconds."
                )
            else:
                del self.blocked_ips[client_ip]
        
        # Periodic cleanup
        async with self._cleanup_lock:
            self._cleanup_old_requests(self.request_counts[client_ip])
            self._cleanup_old_requests(self.chat_counts[client_ip])
        
        # Check general rate limit
        if len(self.request_counts[client_ip]) >= self.requests_per_minute:
            # Exponential backoff: block for increasing duration
            violation_count = len(self.request_counts[client_ip]) - self.requests_per_minute + 1
            block_duration = min(60 * (2 ** min(violation_count, 5)), 3600)  # Max 1 hour
            self.blocked_ips[client_ip] = current_time + block_duration
            
            from app.services import logging_service
            logging_service.log_security_event(
                "rate_limit_exceeded",
                severity="warning",
                context={"ip": client_ip, "block_duration": block_duration}
            )
            
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {block_duration} seconds."
            )
        
        # Check chat-specific rate limit
        if request.url.path == "/api/chat":
            if len(self.chat_counts[client_ip]) >= self.chat_requests_per_minute:
                raise HTTPException(
                    status_code=429,
                    detail="Chat rate limit exceeded. Please slow down."
                )
            self.chat_counts[client_ip].append(current_time)
        
        # Record request
        self.request_counts[client_ip].append(current_time)
        
        return await call_next(request)
    
    def add_to_whitelist(self, ip: str):
        """Add IP to whitelist"""
        self.whitelist.add(ip)
    
    def remove_from_whitelist(self, ip: str):
        """Remove IP from whitelist"""
        self.whitelist.discard(ip)
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        return {
            "active_ips": len(self.request_counts),
            "blocked_ips": len(self.blocked_ips),
            "whitelisted_ips": len(self.whitelist)
        }
