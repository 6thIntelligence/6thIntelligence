"""
Logging Middleware for FastAPI
Automatically logs all requests and responses
"""
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from app.services import logging_service

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = logging_service.generate_request_id()
        
        # Store request ID in state for access in routes
        request.state.request_id = request_id
        
        # Get client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Log incoming request
        logging_service.log_request(
            request_id=request_id,
            endpoint=str(request.url.path),
            method=request.method,
            user_agent=user_agent,
            ip_address=client_ip,
            extra={"query_params": str(request.query_params)}
        )
        
        # Track response time
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Log response
            logging_service.log_response(
                request_id=request_id,
                status_code=response.status_code,
                response_time_ms=response_time_ms
            )
            
            # Add request ID header for debugging
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            
            # Log error
            import traceback
            logging_service.log_error(
                error_type=type(e).__name__,
                message=str(e),
                stack_trace=traceback.format_exc(),
                context={"endpoint": str(request.url.path)},
                request_id=request_id
            )
            
            raise
