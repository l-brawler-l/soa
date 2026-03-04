from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.middleware import LoggingMiddleware
from app.routers import auth, products, orders, promo_codes
from app.errors import MarketplaceException

# Create FastAPI app
app = FastAPI(
    title="Marketplace API",
    description="API for marketplace with products, orders, and promo codes",
    version="1.0.0"
)

# Add middleware
app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(promo_codes.router)


# Exception handlers
@app.exception_handler(MarketplaceException)
async def marketplace_exception_handler(request: Request, exc: MarketplaceException):
    """Handle custom marketplace exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    errors = {}
    for error in exc.errors():
        field = ".".join(str(x) for x in error["loc"][1:])  # Skip 'body'
        errors[field] = error["msg"]

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Validation error",
            "details": errors
        }
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Marketplace API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}
