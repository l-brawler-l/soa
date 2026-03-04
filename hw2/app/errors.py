from typing import Optional, Dict, Any
from fastapi import HTTPException, status


class MarketplaceException(HTTPException):
    """Base exception for marketplace errors"""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.message = message
        self.details = details
        super().__init__(
            status_code=status_code,
            detail={
                "error_code": error_code,
                "message": message,
                "details": details
            }
        )


# Product errors
class ProductNotFoundException(MarketplaceException):
    def __init__(self, product_id: str):
        super().__init__(
            error_code="PRODUCT_NOT_FOUND",
            message=f"Product with ID {product_id} not found",
            status_code=status.HTTP_404_NOT_FOUND
        )


class ProductInactiveException(MarketplaceException):
    def __init__(self, product_id: str):
        super().__init__(
            error_code="PRODUCT_INACTIVE",
            message=f"Product with ID {product_id} is not active",
            status_code=status.HTTP_409_CONFLICT
        )


# Order errors
class OrderNotFoundException(MarketplaceException):
    def __init__(self, order_id: str):
        super().__init__(
            error_code="ORDER_NOT_FOUND",
            message=f"Order with ID {order_id} not found",
            status_code=status.HTTP_404_NOT_FOUND
        )


class OrderLimitExceededException(MarketplaceException):
    def __init__(self, operation_type: str, minutes: int):
        super().__init__(
            error_code="ORDER_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded for {operation_type}. Please wait {minutes} minutes.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )


class OrderHasActiveException(MarketplaceException):
    def __init__(self):
        super().__init__(
            error_code="ORDER_HAS_ACTIVE",
            message="User already has an active order (CREATED or PAYMENT_PENDING)",
            status_code=status.HTTP_409_CONFLICT
        )


class InvalidStateTransitionException(MarketplaceException):
    def __init__(self, current_status: str, attempted_action: str):
        super().__init__(
            error_code="INVALID_STATE_TRANSITION",
            message=f"Cannot perform {attempted_action} on order with status {current_status}",
            status_code=status.HTTP_409_CONFLICT
        )


class InsufficientStockException(MarketplaceException):
    def __init__(self, details: Dict[str, Any]):
        super().__init__(
            error_code="INSUFFICIENT_STOCK",
            message="Insufficient stock for one or more products",
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


# Promo code errors
class PromoCodeInvalidException(MarketplaceException):
    def __init__(self, reason: str):
        super().__init__(
            error_code="PROMO_CODE_INVALID",
            message=f"Promo code is invalid: {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


class PromoCodeMinAmountException(MarketplaceException):
    def __init__(self, min_amount: float, current_amount: float):
        super().__init__(
            error_code="PROMO_CODE_MIN_AMOUNT",
            message=f"Order amount {current_amount} is below minimum required {min_amount}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


# Access errors
class OrderOwnershipViolationException(MarketplaceException):
    def __init__(self):
        super().__init__(
            error_code="ORDER_OWNERSHIP_VIOLATION",
            message="Order belongs to another user",
            status_code=status.HTTP_403_FORBIDDEN
        )


class AccessDeniedException(MarketplaceException):
    def __init__(self, message: str = "Access denied"):
        super().__init__(
            error_code="ACCESS_DENIED",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN
        )


# Validation errors
class ValidationErrorException(MarketplaceException):
    def __init__(self, details: Dict[str, Any]):
        super().__init__(
            error_code="VALIDATION_ERROR",
            message="Validation error",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


# Auth errors
class TokenExpiredException(MarketplaceException):
    def __init__(self):
        super().__init__(
            error_code="TOKEN_EXPIRED",
            message="Access token has expired",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class TokenInvalidException(MarketplaceException):
    def __init__(self):
        super().__init__(
            error_code="TOKEN_INVALID",
            message="Invalid access token",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class RefreshTokenInvalidException(MarketplaceException):
    def __init__(self):
        super().__init__(
            error_code="REFRESH_TOKEN_INVALID",
            message="Invalid refresh token",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
