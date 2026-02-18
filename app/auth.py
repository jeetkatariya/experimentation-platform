"""
JWT Authentication for the Experimentation API.

Provides:
- Token creation with configurable expiration
- Token validation and decoding
- Role-based access control dependencies
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings


security_scheme = HTTPBearer(
    scheme_name="Bearer",
    description="JWT token authentication. Get a token from POST /auth/token"
)


class TokenData(BaseModel):
    """Decoded token information available in routes."""
    user_id: str
    role: str
    exp: datetime


class TokenResponse(BaseModel):
    """Response model for token generation."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str


def create_access_token(
    user_id: str, 
    role: str = "user",
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a new JWT access token.
    
    Args:
        user_id: Unique identifier for the user/service
        role: User role (e.g., "user", "admin")
        expires_delta: Custom expiration time (defaults to config value)
    
    Returns:
        Encoded JWT token string
    
    Example:
        token = create_access_token("user-123", role="admin")
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)
    
    payload = {
        "sub": user_id,      
        "role": role,        
        "exp": expire,       
        "iat": datetime.utcnow(),  
        "type": "access"     
    }
    
    token = jwt.encode(
        payload, 
        settings.jwt_secret_key, 
        algorithm=settings.jwt_algorithm
    )
    return token


def decode_token(token: str) -> TokenData:
    """
    Decode and validate a JWT token.
    
    Args:
        token: The JWT token string
        
    Returns:
        TokenData with user_id, role, and expiration
        
    Raises:
        HTTPException: If token is invalid, expired, or malformed
    """
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        
        user_id = payload.get("sub")
        role = payload.get("role", "user")
        exp = payload.get("exp")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return TokenData(
            user_id=user_id, 
            role=role,
            exp=datetime.fromtimestamp(exp) if exp else datetime.utcnow()
        )
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme)
) -> TokenData:
    """
    FastAPI dependency that validates JWT and returns decoded data.
    
    Usage in routes:
        @router.get("/protected")
        async def protected_route(current_user: TokenData = Depends(verify_token)):
            print(f"User: {current_user.user_id}, Role: {current_user.role}")
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    return decode_token(token)


async def require_admin(
    current_user: TokenData = Depends(verify_token)
) -> TokenData:
    """
    FastAPI dependency that requires admin role.
    
    Usage:
        @router.delete("/dangerous")
        async def admin_only(current_user: TokenData = Depends(require_admin)):
            # Only admins reach here
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def get_current_user_id(current_user: TokenData = Depends(verify_token)) -> str:
    """Convenience dependency to get just the user_id."""
    return current_user.user_id
