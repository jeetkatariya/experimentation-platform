"""
Application configuration management.
Uses pydantic-settings for environment variable parsing with validation.

All sensitive configuration should be stored in .env file (never commit to git).
See .env.example for required variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Required environment variables:
    - JWT_SECRET_KEY: Secret key for signing JWT tokens
    
    Optional (have defaults):
    - DATABASE_URL: Database connection string
    - JWT_ALGORITHM: Algorithm for JWT (default: HS256)
    - JWT_EXPIRATION_MINUTES: Token expiry in minutes (default: 60)
    - API_TITLE, API_VERSION, LOG_LEVEL: API metadata
    """
    
    database_url: str = Field(
        default="sqlite:///./experimentation.db",
        description="Database connection URL"
    )
    
    api_title: str = Field(default="Experimentation API")
    api_version: str = Field(default="1.0.0")
    api_description: str = Field(default="A/B Testing and Experimentation Platform")
    
    jwt_secret_key: str = Field(
        ...,  
        description="Secret key for JWT signing. Generate with: openssl rand -hex 32"
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm for JWT encoding"
    )
    jwt_expiration_minutes: int = Field(
        default=60,
        description="JWT token expiration time in minutes"
    )
    
    log_level: str = Field(default="INFO")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  



settings = Settings()

