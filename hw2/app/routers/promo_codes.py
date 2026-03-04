from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PromoCode, User, UserRole
from app.schemas import PromoCodeCreate, PromoCodeResponse
from app.auth import require_role

router = APIRouter(prefix="/promo-codes", tags=["Promo Codes"])


@router.post("", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED)
def create_promo_code(
    promo_data: PromoCodeCreate,
    current_user: User = Depends(require_role(UserRole.SELLER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    """Create a new promo code (SELLER and ADMIN only)"""
    new_promo = PromoCode(
        code=promo_data.code,
        discount_type=promo_data.discount_type,
        discount_value=promo_data.discount_value,
        min_order_amount=promo_data.min_order_amount,
        max_uses=promo_data.max_uses,
        current_uses=0,
        valid_from=promo_data.valid_from,
        valid_until=promo_data.valid_until,
        active=promo_data.active
    )

    db.add(new_promo)
    db.commit()
    db.refresh(new_promo)

    return new_promo
