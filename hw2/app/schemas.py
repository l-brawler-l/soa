from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, field_validator
from app.models import UserRole, ProductStatus, OrderStatus, DiscountType


# Authentication schemas
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    role: UserRole


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    created_at: datetime

    class Config:
        from_attributes = True


# Product schemas
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    price: Decimal = Field(..., gt=0)
    stock: int = Field(..., ge=0)
    category: str = Field(..., min_length=1, max_length=100)
    status: ProductStatus


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    price: Optional[Decimal] = Field(None, gt=0)
    stock: Optional[int] = Field(None, ge=0)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    status: Optional[ProductStatus] = None


class ProductResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    price: Decimal
    stock: int
    category: str
    status: ProductStatus
    seller_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total_elements: int
    page: int
    size: int


# Order schemas
class OrderItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(..., ge=1, le=999)


class OrderCreate(BaseModel):
    items: List[OrderItemCreate] = Field(..., min_length=1, max_length=50)
    promo_code: Optional[str] = Field(None, pattern=r'^[A-Z0-9_]{4,20}$')


class OrderUpdate(BaseModel):
    items: List[OrderItemCreate] = Field(..., min_length=1, max_length=50)


class OrderItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    quantity: int
    price_at_order: Decimal

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: UUID
    user_id: UUID
    status: OrderStatus
    items: List[OrderItemResponse]
    promo_code_id: Optional[UUID]
    total_amount: Decimal
    discount_amount: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Promo code schemas
class PromoCodeCreate(BaseModel):
    code: str = Field(..., pattern=r'^[A-Z0-9_]{4,20}$')
    discount_type: DiscountType
    discount_value: Decimal = Field(..., gt=0)
    min_order_amount: Decimal = Field(..., ge=0)
    max_uses: int = Field(..., ge=1)
    valid_from: datetime
    valid_until: datetime
    active: bool = True


class PromoCodeResponse(BaseModel):
    id: UUID
    code: str
    discount_type: DiscountType
    discount_value: Decimal
    min_order_amount: Decimal
    max_uses: int
    current_uses: int
    valid_from: datetime
    valid_until: datetime
    active: bool

    class Config:
        from_attributes = True


# Error schema
class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[dict] = None
