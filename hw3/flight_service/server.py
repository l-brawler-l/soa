"""gRPC server for Flight Service."""
import logging
import sys
from concurrent import futures
import grpc
import time

from .config import settings
from .database import init_db
from .service import FlightServiceServicer
from .auth import create_auth_interceptor
import flight_service_pb2_grpc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def serve():
    """Start the gRPC server."""
    # Initialize database
    logger.info("Initializing database...")
    max_retries = 5
    for i in range(max_retries):
        try:
            init_db()
            break
        except Exception as e:
            if i < max_retries - 1:
                logger.warning(f"Database initialization failed (attempt {i+1}/{max_retries}): {e}")
                time.sleep(5)
            else:
                logger.error(f"Database initialization failed after {max_retries} attempts")
                raise

    # Create server with auth interceptor
    auth_interceptor = create_auth_interceptor()
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=(auth_interceptor,)
    )

    # Add servicer
    flight_service_pb2_grpc.add_FlightServiceServicer_to_server(
        FlightServiceServicer(), server
    )

    # Bind to port
    server.add_insecure_port(f'[::]:{settings.grpc_port}')

    logger.info(f"Starting Flight Service gRPC server on port {settings.grpc_port}")
    server.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.stop(0)


if __name__ == '__main__':
    serve()
