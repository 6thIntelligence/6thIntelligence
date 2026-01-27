"""
Security Headers Middleware
Adds standard security headers to all responses to prevent common web attacks.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Prevent clickjacking - Allow framing only from the same origin to support the widget
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Enable XSS protection (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # HSTS (Strict Transport Security) - 1 year
        # Only effective if served over HTTPS, but good practice to include
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy (CSP)
        # Verify strict enough to be secure but permissive enough for the app
        # Allowing unsafe-inline for styles/scripts is often necessary for some UI libs, 
        # but we try to be strict.
        csp_directives = [
            "default-src 'self'",
            "img-src 'self' data: https: blob:",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", 
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com", # unsafe-eval often needed for some dynamic UIs
            "font-src 'self' https://fonts.gstatic.com",
            "connect-src 'self' https://openrouter.ai", # Allow connections to API
            "frame-ancestors 'self'", # Changed from 'none' to 'self' to allow the widget iframe
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions Policy (limiting browser features)
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        
        return response
