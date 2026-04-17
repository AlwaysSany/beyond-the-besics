"""
FastAPI 2FA Demo Server.

A complete multi-factor authentication system implementing TOTP (RFC 6238)
with QR code onboarding — compatible with Google Authenticator, Authy, etc.

Endpoints:
    POST /register       → Register a new user
    GET  /enable-2fa/{u} → Get QR code to scan with authenticator app
    POST /verify-2fa     → Confirm OTP to activate 2FA
    POST /login          → Login (step 1: password)
    POST /login-2fa      → Login (step 2: OTP verification)
"""

import hashlib
import io

import qrcode
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from database import users_db
from models import OTPVerify, UserCreate, UserLogin
from security import generate_otpauth_uri, generate_secret, verify_totp

app = FastAPI(
    title="Multi-Factor Authentication Demo",
    description="A TOTP-based 2FA system built from scratch for educational purposes.",
    version="1.0.0",
)


def hash_password(password: str) -> str:
    """Hash a password using SHA-256.

    Note: In production, use bcrypt or argon2 for password hashing.
    SHA-256 is used here for simplicity as this is a demo.
    """
    return hashlib.sha256(password.encode()).hexdigest()


# ─────────────────────────────────────────────
# Phase 1: User Registration
# ─────────────────────────────────────────────


@app.post("/register")
def register(user: UserCreate) -> dict:
    """Register a new user with username + password.

    A unique TOTP secret is generated and stored for the user,
    but 2FA is not enabled until they verify an OTP code.
    """
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="User already exists")

    secret = generate_secret()

    users_db[user.username] = {
        "password": hash_password(user.password),
        "secret": secret,
        "2fa_enabled": False,
    }

    return {"message": "User registered", "username": user.username}


# ─────────────────────────────────────────────
# Phase 2: 2FA Enrollment (QR Code + Verify)
# ─────────────────────────────────────────────


@app.get("/enable-2fa/{username}")
def enable_2fa(username: str) -> StreamingResponse:
    """Generate a QR code for the user to scan with their authenticator app.

    The QR encodes an otpauth:// URI containing the shared secret.
    After scanning, the user's authenticator app will start generating
    TOTP codes that match the server's expected codes.
    """
    user = users_db.get(username)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    uri = generate_otpauth_uri(user["secret"], username)

    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf)
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")


@app.post("/verify-2fa")
def verify_2fa(data: OTPVerify) -> dict:
    """Confirm the OTP code to activate 2FA for the user.

    The user enters the 6-digit code from their authenticator app.
    If it matches, 2FA is enabled on their account.
    """
    user = users_db.get(data.username)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if verify_totp(user["secret"], data.otp):
        user["2fa_enabled"] = True
        return {"message": "2FA enabled successfully"}

    raise HTTPException(status_code=400, detail="Invalid OTP")


# ─────────────────────────────────────────────
# Phase 3: Login Flow
# ─────────────────────────────────────────────


@app.post("/login")
def login(user: UserLogin) -> dict:
    """Login step 1: Verify username + password.

    If 2FA is enabled, the client must follow up with /login-2fa.
    """
    db_user = users_db.get(user.username)

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if db_user["password"] != hash_password(user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if db_user["2fa_enabled"]:
        return {"message": "Enter OTP", "2fa_required": True}

    return {"message": "Login successful", "2fa_required": False}


@app.post("/login-2fa")
def login_2fa(data: OTPVerify) -> dict:
    """Login step 2: Verify the TOTP code.

    Only called when the user has 2FA enabled.
    """
    user = users_db.get(data.username)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if verify_totp(user["secret"], data.otp):
        return {"message": "Login successful"}

    raise HTTPException(status_code=401, detail="Invalid OTP")
