"""
Pydantic request/response models for the 2FA API.

Validates all incoming request data using strict type hints.
"""

from pydantic import BaseModel


class UserCreate(BaseModel):
    """Request body for user registration."""

    username: str
    password: str


class UserLogin(BaseModel):
    """Request body for standard login (step 1)."""

    username: str
    password: str


class OTPVerify(BaseModel):
    """Request body for OTP verification (setup confirmation + login step 2)."""

    username: str
    otp: str
