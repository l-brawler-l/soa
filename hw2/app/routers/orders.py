from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.models import (
    Order, OrderItem, Product, PromoCode, User, UserOperation,
    UserRole, OrderStatus, ProductStatus, OperationType, DiscountType
)
from app.schemas import OrderCreate, OrderUpdate, OrderResponse
from app.auth import get_current_user, require_role
from app.config import settings
from app.errors import (
    OrderNotFoundException,
    OrderLimitExceededException,
    OrderHasActiveException,
    ProductNotFoundException,
    ProductInactiveException,
    InsufficientStockException,
    PromoCodeInvalidException,
    PromoCodeMinAmountException,
    OrderOwnershipViolationException,
    InvalidStateTransitionException,
    AccessDeniedException
)

router = APIRouter(prefix="/orders", tags=["Orders"])


def check_rate_limit(user_id: UUID, operation_type: OperationType, db: Session):
    """Check if user has exceeded rate limit for operation"""
    last_operation = (
        db.query(UserOperation)
        .filter(
            and_(
                UserOperation.user_id == user_id,
                UserOperation.operation_type == operation_type
            )
        )
        .order_by(UserOperation.created_at.desc())
        .first()
    )

    if last_operation:
        time_diff = datetime.now(timezone.utc) - last_operation.created_at
        if time_diff < timedelta(minutes=settings.ORDER_RATE_LIMIT_MINUTES):
            raise OrderLimitExceededException(
                operation_type.value,
                settings.ORDER_RATE_LIMIT_MINUTES
            )


def check_active_orders(user_id: UUID, db: Session):
    """Check if user has active orders"""
    active_order = (
        db.query(Order)
        .filter(
            and_(
                Order.user_id == user_id,
                or_(
                    Order.status == OrderStatus.CREATED,
                    Order.status == OrderStatus.PAYMENT_PENDING
                )
            )
        )
        .first()
    )

    if active_order:
        raise OrderHasActiveException()


def validate_and_reserve_products(items: List, db: Session) -> tuple:
    """Validate products and reserve stock, return products and total"""
    products_data = []
    insufficient_stock = []

    for item in items:
        product = db.query(Product).filter(Product.id == item.product_id).first()

        if not product:
            raise ProductNotFoundException(str(item.product_id))

        if product.status != ProductStatus.ACTIVE:
            raise ProductInactiveException(str(item.product_id))

        if product.stock < item.quantity:
            insufficient_stock.append({
                "product_id": str(item.product_id),
                "requested": item.quantity,
                "available": product.stock
            })

        products_data.append((product, item.quantity))

    if insufficient_stock:
        raise InsufficientStockException({"products": insufficient_stock})

    # Reserve stock
    total_amount = Decimal("0")
    for product, quantity in products_data:
        product.stock -= quantity
        total_amount += product.price * quantity

    return products_data, total_amount


def apply_promo_code(promo_code_str: str, total_amount: Decimal, db: Session):
    """Validate and apply promo code, return promo_code, discount_amount, final_total"""
    promo_code = db.query(PromoCode).filter(PromoCode.code == promo_code_str).first()

    if not promo_code:
        raise PromoCodeInvalidException("Promo code not found")

    if not promo_code.active:
        raise PromoCodeInvalidException("Promo code is not active")

    if promo_code.current_uses >= promo_code.max_uses:
        raise PromoCodeInvalidException("Promo code usage limit exceeded")

    now = datetime.now(timezone.utc)
    if now < promo_code.valid_from or now > promo_code.valid_until:
        raise PromoCodeInvalidException("Promo code has expired or not yet valid")

    if total_amount < promo_code.min_order_amount:
        raise PromoCodeMinAmountException(
            float(promo_code.min_order_amount),
            float(total_amount)
        )

    # Calculate discount
    if promo_code.discount_type == DiscountType.PERCENTAGE:
        discount = total_amount * promo_code.discount_value / Decimal("100")
        # Max 70% discount
        max_discount = total_amount * Decimal("0.7")
        if discount > max_discount:
            discount = total_amount  # Set to 100% as per spec
        discount_amount = discount
    else:  # FIXED_AMOUNT
        discount_amount = min(promo_code.discount_value, total_amount)

    final_total = total_amount - discount_amount

    # Increment usage
    promo_code.current_uses += 1

    return promo_code, discount_amount, final_total


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: OrderCreate,
    current_user: User = Depends(require_role(UserRole.USER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    """Create a new order with full business logic validation"""
    try:
        # 1. Check rate limit
        check_rate_limit(current_user.id, OperationType.CREATE_ORDER, db)

        # 2. Check active orders
        check_active_orders(current_user.id, db)

        # 3-5. Validate products and reserve stock
        products_data, total_amount = validate_and_reserve_products(order_data.items, db)

        # 6. Create order
        new_order = Order(
            user_id=current_user.id,
            status=OrderStatus.CREATED,
            total_amount=total_amount,
            discount_amount=Decimal("0")
        )

        # 7. Apply promo code if provided
        if order_data.promo_code:
            promo_code, discount_amount, final_total = apply_promo_code(
                order_data.promo_code,
                total_amount,
                db
            )
            new_order.promo_code_id = promo_code.id
            new_order.discount_amount = discount_amount
            new_order.total_amount = final_total

        db.add(new_order)
        db.flush()  # Get order ID

        # Create order items with price snapshot
        for product, quantity in products_data:
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=product.id,
                quantity=quantity,
                price_at_order=product.price
            )
            db.add(order_item)

        # 8. Record operation
        operation = UserOperation(
            user_id=current_user.id,
            operation_type=OperationType.CREATE_ORDER
        )
        db.add(operation)

        db.commit()
        db.refresh(new_order)

        return new_order
    except Exception as e:
        db.rollback()
        raise e


@router.get("/{id}", response_model=OrderResponse)
def get_order(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get order by ID (USER sees only own, ADMIN sees any)"""
    order = db.query(Order).filter(Order.id == id).first()
    if not order:
        raise OrderNotFoundException(str(id))

    # Check ownership
    if current_user.role == UserRole.USER and order.user_id != current_user.id:
        raise OrderOwnershipViolationException()

    # SELLER cannot access orders
    if current_user.role == UserRole.SELLER:
        raise AccessDeniedException("Sellers cannot access orders")

    return order


@router.put("/{id}", response_model=OrderResponse)
def update_order(
    id: UUID,
    order_data: OrderUpdate,
    current_user: User = Depends(require_role(UserRole.USER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    """Update order (only in CREATED status)"""
    try:
        order = db.query(Order).filter(Order.id == id).first()
        if not order:
            raise OrderNotFoundException(str(id))

        # 1. Check ownership
        if current_user.role == UserRole.USER and order.user_id != current_user.id:
            raise OrderOwnershipViolationException()

        # 2. Check status
        if order.status != OrderStatus.CREATED:
            raise InvalidStateTransitionException(order.status.value, "update")

        # 3. Check rate limit
        check_rate_limit(current_user.id, OperationType.UPDATE_ORDER, db)

        # 4. Return previous stock
        for item in order.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product.stock += item.quantity

        # Delete old items
        for item in order.items:
            db.delete(item)

        # 5. Validate and reserve new products
        products_data, total_amount = validate_and_reserve_products(order_data.items, db)

        # 6. Recalculate with promo code if exists
        if order.promo_code_id:
            promo_code = db.query(PromoCode).filter(PromoCode.id == order.promo_code_id).first()
            if promo_code and total_amount >= promo_code.min_order_amount:
                # Recalculate discount
                if promo_code.discount_type == DiscountType.PERCENTAGE:
                    discount = total_amount * promo_code.discount_value / Decimal("100")
                    max_discount = total_amount * Decimal("0.7")
                    if discount > max_discount:
                        discount = total_amount
                    discount_amount = discount
                else:
                    discount_amount = min(promo_code.discount_value, total_amount)

                order.discount_amount = discount_amount
                order.total_amount = total_amount - discount_amount
            else:
                # Remove promo code if no longer applicable
                if promo_code:
                    promo_code.current_uses -= 1
                order.promo_code_id = None
                order.discount_amount = Decimal("0")
                order.total_amount = total_amount
        else:
            order.total_amount = total_amount

        # Create new order items
        for product, quantity in products_data:
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                price_at_order=product.price
            )
            db.add(order_item)

        # 7. Record operation
        operation = UserOperation(
            user_id=current_user.id,
            operation_type=OperationType.UPDATE_ORDER
        )
        db.add(operation)

        db.commit()
        db.refresh(order)

        return order
    except Exception as e:
        db.rollback()
        raise e


@router.post("/{id}/cancel", response_model=OrderResponse)
def cancel_order(
    id: UUID,
    current_user: User = Depends(require_role(UserRole.USER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    """Cancel order (only from CREATED or PAYMENT_PENDING status)"""
    try:
        order = db.query(Order).filter(Order.id == id).first()
        if not order:
            raise OrderNotFoundException(str(id))

        # 1. Check ownership
        if current_user.role == UserRole.USER and order.user_id != current_user.id:
            raise OrderOwnershipViolationException()

        # 2. Check status
        if order.status not in [OrderStatus.CREATED, OrderStatus.PAYMENT_PENDING]:
            raise InvalidStateTransitionException(order.status.value, "cancel")

        # 3. Return stock
        for item in order.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product.stock += item.quantity

        # 4. Return promo code usage
        if order.promo_code_id:
            promo_code = db.query(PromoCode).filter(PromoCode.id == order.promo_code_id).first()
            if promo_code:
                promo_code.current_uses -= 1

        # 5. Set status to CANCELED
        order.status = OrderStatus.CANCELED

        db.commit()
        db.refresh(order)

        return order
    except Exception as e:
        db.rollback()
        raise e
