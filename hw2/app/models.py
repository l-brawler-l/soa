import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, ForeignKey, Enum as SQLEnum, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class UserRole(str, enum.Enum):
    USER = "USER"
    SELLER = "SELLER"
    ADMIN = "ADMIN"


class ProductStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class OrderStatus(str, enum.Enum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class OperationType(str, enum.Enum):
    CREATE_ORDER = "CREATE_ORDER"
    UPDATE_ORDER = "UPDATE_ORDER"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    products = relationship("Product", back_populates="seller")
    orders = relationship("Order", back_populates="user")
    operations = relationship("UserOperation", back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(4000), nullable=True)
    price = Column(Numeric(12, 2), nullable=False)
    stock = Column(Integer, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    status = Column(SQLEnum(ProductStatus), nullable=False, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    seller = relationship("User", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")

    __table_args__ = (
        CheckConstraint('price > 0', name='check_price_positive'),
        CheckConstraint('stock >= 0', name='check_stock_non_negative'),
    )


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(20), unique=True, nullable=False, index=True)
    discount_type = Column(SQLEnum(DiscountType), nullable=False)
    discount_value = Column(Numeric(12, 2), nullable=False)
    min_order_amount = Column(Numeric(12, 2), nullable=False)
    max_uses = Column(Integer, nullable=False)
    current_uses = Column(Integer, nullable=False, default=0)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    active = Column(Boolean, nullable=False, default=True)

    # Relationships
    orders = relationship("Order", back_populates="promo_code")

    __table_args__ = (
        CheckConstraint('discount_value > 0', name='check_discount_value_positive'),
        CheckConstraint('min_order_amount >= 0', name='check_min_order_amount_non_negative'),
        CheckConstraint('max_uses > 0', name='check_max_uses_positive'),
        CheckConstraint('current_uses >= 0', name='check_current_uses_non_negative'),
        CheckConstraint('current_uses <= max_uses', name='check_current_uses_not_exceed_max'),
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(SQLEnum(OrderStatus), nullable=False, index=True)
    promo_code_id = Column(UUID(as_uuid=True), ForeignKey("promo_codes.id", ondelete="SET NULL"), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=False)
    discount_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="orders")
    promo_code = relationship("PromoCode", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint('total_amount >= 0', name='check_total_amount_non_negative'),
        CheckConstraint('discount_amount >= 0', name='check_discount_amount_non_negative'),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    price_at_order = Column(Numeric(12, 2), nullable=False)

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

    __table_args__ = (
        CheckConstraint('quantity > 0', name='check_quantity_positive'),
        CheckConstraint('price_at_order > 0', name='check_price_at_order_positive'),
    )


class UserOperation(Base):
    __tablename__ = "user_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_type = Column(SQLEnum(OperationType), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="operations")
