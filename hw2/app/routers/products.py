from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.models import Product, User, UserRole, ProductStatus
from app.schemas import ProductCreate, ProductUpdate, ProductResponse, ProductListResponse
from app.auth import get_current_user, require_role
from app.errors import ProductNotFoundException, AccessDeniedException

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    page: int = Query(0, ge=0, description="Page number starting from 0"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    status: Optional[ProductStatus] = Query(None, description="Filter by status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of products with pagination and filtering"""
    # Build query
    query = db.query(Product)

    # Apply filters
    if status:
        query = query.filter(Product.status == status)
    if category:
        query = query.filter(Product.category == category)

    # Get total count
    total_elements = query.count()

    # Apply pagination
    products = query.offset(page * size).limit(size).all()

    return ProductListResponse(
        items=products,
        total_elements=total_elements,
        page=page,
        size=size
    )


@router.get("/{id}", response_model=ProductResponse)
def get_product(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product by ID"""
    product = db.query(Product).filter(Product.id == id).first()
    if not product:
        raise ProductNotFoundException(str(id))

    return product


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(require_role(UserRole.SELLER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    """Create a new product (SELLER creates own, ADMIN creates any)"""
    # Create product
    new_product = Product(
        name=product_data.name,
        description=product_data.description,
        price=product_data.price,
        stock=product_data.stock,
        category=product_data.category,
        status=product_data.status,
        seller_id=current_user.id if current_user.role == UserRole.SELLER else None
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return new_product


@router.put("/{id}", response_model=ProductResponse)
def update_product(
    id: UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(require_role(UserRole.SELLER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    """Update product (SELLER updates only own, ADMIN updates any)"""
    product = db.query(Product).filter(Product.id == id).first()
    if not product:
        raise ProductNotFoundException(str(id))

    # Check ownership for SELLER
    if current_user.role == UserRole.SELLER:
        if product.seller_id != current_user.id:
            raise AccessDeniedException("You can only update your own products")

    # Update fields
    update_data = product_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    id: UUID,
    current_user: User = Depends(require_role(UserRole.SELLER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    """Soft delete product by setting status to ARCHIVED (SELLER deletes only own, ADMIN deletes any)"""
    product = db.query(Product).filter(Product.id == id).first()
    if not product:
        raise ProductNotFoundException(str(id))

    # Check ownership for SELLER
    if current_user.role == UserRole.SELLER:
        if product.seller_id != current_user.id:
            raise AccessDeniedException("You can only delete your own products")

    # Soft delete by setting status to ARCHIVED
    product.status = ProductStatus.ARCHIVED
    db.commit()

    return None
