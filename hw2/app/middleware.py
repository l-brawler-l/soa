import json
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging

# Configure JSON logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging API requests in JSON format"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Record start time
        start_time = time.time()

        # Get user_id if available (will be set by auth)
        user_id = None

        # Read request body for mutating requests
        request_body = None
        if request.method in ["POST", "PUT", "DELETE"]:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    request_body = json.loads(body_bytes.decode())
                    # Mask sensitive data
                    if isinstance(request_body, dict):
                        if "password" in request_body:
                            request_body["password"] = "***MASKED***"
                        if "hashed_password" in request_body:
                            request_body["hashed_password"] = "***MASKED***"
            except:
                request_body = None

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Try to get user_id from request state (set by auth middleware)
        if hasattr(request.state, "user"):
            user_id = str(request.state.user.id)

        # Create log entry
        log_entry = {
            "request_id": request_id,
            "method": request.method,
            "endpoint": str(request.url.path),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        }

        # Add request body for mutating requests
        if request_body is not None:
            log_entry["request_body"] = request_body

        # Log as JSON
        logger.info(json.dumps(log_entry))

        # Add request ID to response headers
        response.headers["X-Request-Id"] = request_id

        return response
