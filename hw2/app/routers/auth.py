from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserRegister, UserLogin, UserResponse, TokenResponse, RefreshTokenRequest
from app.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.errors import TokenInvalidException, RefreshTokenInvalidException

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "VALIDATION_ERROR",
                "message": "Email already registered",
                "details": {"email": "Email already exists"}
            }
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        role=user_data.role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login and get access and refresh tokens"""
    # Find user
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "TOKEN_INVALID",
                "message": "Invalid email or password"
            }
        )

    # Create tokens
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(token_data: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Refresh access token using refresh token"""
    try:
        payload = decode_token(token_data.refresh_token)

        # Check token type
        if payload.get("type") != "refresh":
            raise RefreshTokenInvalidException()

        user_id = payload.get("sub")
        if not user_id:
            raise RefreshTokenInvalidException()

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise RefreshTokenInvalidException()

        # Create new tokens
        access_token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    except Exception:
        raise RefreshTokenInvalidException()
