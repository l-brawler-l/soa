"""Authentication interceptor for gRPC."""
import grpc
import logging
from typing import Callable, Any

from .config import settings

logger = logging.getLogger(__name__)


class AuthInterceptor(grpc.ServerInterceptor):
    """gRPC server interceptor for API key authentication."""

    def __init__(self, api_key: str):
        """
        Initialize auth interceptor.

        Args:
            api_key: Expected API key for authentication
        """
        self.api_key = api_key

    def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails
    ) -> grpc.RpcMethodHandler:
        """
        Intercept gRPC calls to check authentication.

        Args:
            continuation: Next handler in the chain
            handler_call_details: Details about the RPC call

        Returns:
            RPC method handler
        """
        # Get metadata from the call
        metadata = dict(handler_call_details.invocation_metadata)

        # Check for API key in metadata
        api_key = metadata.get('x-api-key', '')

        if api_key != self.api_key:
            logger.warning(f"Unauthorized access attempt to {handler_call_details.method}")

            def abort(request, context):
                context.abort(
                    grpc.StatusCode.UNAUTHENTICATED,
                    "Invalid or missing API key"
                )

            return grpc.unary_unary_rpc_method_handler(
                abort,
                request_deserializer=lambda x: x,
                response_serializer=lambda x: x
            )

        logger.debug(f"Authenticated request to {handler_call_details.method}")
        return continuation(handler_call_details)


def create_auth_interceptor() -> AuthInterceptor:
    """Create authentication interceptor with settings."""
    return AuthInterceptor(settings.api_key)
