from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole
from app.errors import TokenExpiredException, TokenInvalidException, RefreshTokenInvalidException

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise TokenInvalidException()


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    if not authorization:
        raise TokenInvalidException()

    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise TokenInvalidException()

    token = parts[1]

    try:
        payload = decode_token(token)

        # Check token type
        if payload.get("type") != "access":
            raise TokenInvalidException()

        user_id: str = payload.get("sub")
        if user_id is None:
            raise TokenInvalidException()

        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise TokenInvalidException()

        return user
    except JWTError:
        raise TokenExpiredException()


def require_role(*allowed_roles: UserRole):
    """Dependency to check if user has required role"""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            from app.errors import AccessDeniedException
            raise AccessDeniedException(f"Required role: {', '.join([r.value for r in allowed_roles])}")
        return current_user
    return role_checker


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user if token is provided, otherwise return None"""
    if not authorization:
        return None

    try:
        return get_current_user(authorization, db)
    except:
        return None
