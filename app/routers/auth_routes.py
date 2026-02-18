"""
Authentication endpoints for JWT token management.

Provides endpoints for:
- User login and token generation
- Token refresh (future)
- User registration (demo)
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from passlib.context import CryptContext

from app.auth import create_access_token, TokenResponse
from app.config import settings

router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    """Request body for login."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Request body for user registration."""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)
    role: str = Field(default="user", pattern="^(user|admin)$")


class UserInfo(BaseModel):
    """User information response."""
    username: str
    role: str


# In-memory user store (replace with database in production)
# Passwords are hashed using bcrypt
USERS_DB = {
    "admin": {
        "password_hash": pwd_context.hash("admin123"),
        "role": "admin"
    },
    "user1": {
        "password_hash": pwd_context.hash("user123"),
        "role": "user"
    },
    "testuser": {
        "password_hash": pwd_context.hash("test123"),
        "role": "user"
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


@router.post("/token", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate and receive a JWT token.
    
    **Demo Credentials:**
    - Admin: username=`admin`, password=`admin123`
    - User: username=`user1`, password=`user123`
    - User: username=`testuser`, password=`test123`
    
    **Example:**
    ```
    POST /auth/token
    {
        "username": "admin",
        "password": "admin123"
    }
    ```
    
    **Response:**
    ```json
    {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "bearer",
        "expires_in": 3600,
        "user_id": "admin",
        "role": "admin"
    }
    ```
    """
    user = USERS_DB.get(request.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Create JWT token
    access_token = create_access_token(
        user_id=request.username,
        role=user["role"]
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_minutes * 60,  # Convert to seconds
        user_id=request.username,
        role=user["role"]
    )


@router.post("/register", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """
    Register a new user (demo endpoint).
    
    **Note:** In production, this would:
    - Store users in a database
    - Send verification email
    - Have rate limiting
    - Not allow self-assignment of admin role
    
    **Example:**
    ```
    POST /auth/register
    {
        "username": "newuser",
        "password": "securepass123",
        "role": "user"
    }
    ```
    """
    if request.username in USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # In demo mode, prevent creating admin users via registration
    if request.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot self-register as admin"
        )
    
    # Add user to in-memory store
    USERS_DB[request.username] = {
        "password_hash": get_password_hash(request.password),
        "role": request.role
    }
    
    return UserInfo(
        username=request.username,
        role=request.role
    )


@router.get("/users", response_model=list[UserInfo])
async def list_users():
    """
    List all registered users (demo endpoint).
    
    **Note:** In production, this would require admin authentication.
    """
    return [
        UserInfo(username=username, role=data["role"])
        for username, data in USERS_DB.items()
    ]

