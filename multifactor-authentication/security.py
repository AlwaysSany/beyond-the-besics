"""
Core TOTP (Time-Based One-Time Password) implementation.

Implements RFC 6238 (TOTP) and RFC 4226 (HOTP) — the same standards
used by Google Authenticator, Microsoft Authenticator, and Authy.

No external libraries required — uses only Python standard library.
"""

import time
import hmac
import hashlib
import base64
import struct
import os


def generate_secret() -> str:
    """Generate a cryptographically random Base32-encoded secret key.

    This creates a 160-bit (20 byte) random secret, which is the standard
    length used by Google Authenticator. The secret is Base32-encoded for
    safe embedding in QR codes and otpauth:// URIs.

    Returns:
        str: A Base32-encoded secret key (e.g., "JBSWY3DPEHPK3PXP...")
    """
    return base64.b32encode(os.urandom(20)).decode("utf-8")


def base32_decode(secret: str) -> bytes:
    """Decode a Base32-encoded secret key to raw bytes.

    Handles case-insensitive input and strips any whitespace that
    users might accidentally include when copying secrets manually.

    Args:
        secret: Base32-encoded secret string.

    Returns:
        bytes: The decoded raw secret key.
    """
    secret = secret.replace(" ", "").upper()
    return base64.b32decode(secret, casefold=True)


def int_to_bytes(value: int) -> bytes:
    """Convert an integer to an 8-byte big-endian byte string.

    This is used to convert the time counter into the format required
    by HMAC computation (RFC 4226 Section 5.2).

    Args:
        value: The integer to convert (typically the time counter).

    Returns:
        bytes: 8-byte big-endian representation.
    """
    return struct.pack(">Q", value)


def generate_totp(
    secret: str,
    interval: int = 30,
    digits: int = 6,
    algo: callable = hashlib.sha1,
) -> str:
    """Generate a TOTP code from a shared secret.

    This follows the exact algorithm described in RFC 6238:
      1. Decode the Base32 secret to raw bytes
      2. Compute the time counter: T = floor(unix_time / interval)
      3. Convert T to 8-byte big-endian
      4. Compute HMAC-SHA1(secret, T)
      5. Apply dynamic truncation to extract a 4-byte chunk
      6. Reduce modulo 10^digits to get the final OTP

    Args:
        secret: Base32-encoded shared secret key.
        interval: Time step in seconds (default: 30).
        digits: Number of digits in the OTP (default: 6).
        algo: Hash algorithm for HMAC (default: SHA-1).

    Returns:
        str: Zero-padded OTP string (e.g., "048219").
    """
    # Step 1: Decode base32 secret to raw key bytes
    key = base32_decode(secret)

    # Step 2: Compute time counter (number of intervals since Unix epoch)
    current_time = int(time.time())
    counter = current_time // interval

    # Step 3: Convert counter to 8-byte big-endian
    counter_bytes = int_to_bytes(counter)

    # Step 4: HMAC computation — the core cryptographic operation
    hmac_hash = hmac.new(key, counter_bytes, algo).digest()

    # Step 5: Dynamic truncation (RFC 4226 Section 5.4)
    # Use the last nibble (4 bits) as an offset index
    offset = hmac_hash[-1] & 0x0F
    # Extract 4 bytes starting at that offset
    truncated_hash = hmac_hash[offset : offset + 4]
    # Convert to integer and mask the sign bit (31st bit)
    code_int = struct.unpack(">I", truncated_hash)[0] & 0x7FFFFFFF

    # Step 6: Modulo to get the final N-digit OTP
    otp = code_int % (10**digits)

    # Step 7: Zero-pad to ensure consistent length
    return str(otp).zfill(digits)


def verify_totp(
    secret: str,
    user_code: str,
    window: int = 1,
    interval: int = 30,
    digits: int = 6,
) -> bool:
    """Verify a user-provided TOTP code against the shared secret.

    Checks the current time window plus adjacent windows (T-1, T, T+1)
    to account for small clock drift between client and server.

    Uses hmac.compare_digest() for constant-time comparison to prevent
    timing attacks that could leak information about valid codes.

    Args:
        secret: Base32-encoded shared secret key.
        user_code: The 6-digit OTP string provided by the user.
        window: Number of adjacent time windows to check (default: 1).
        interval: Time step in seconds (default: 30).
        digits: Number of digits in the OTP (default: 6).

    Returns:
        bool: True if the code is valid, False otherwise.
    """
    key = base32_decode(secret)
    current_counter = int(time.time()) // interval

    for offset in range(-window, window + 1):
        counter = current_counter + offset
        counter_bytes = int_to_bytes(counter)

        hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()

        dynamic_offset = hmac_hash[-1] & 0x0F
        truncated = hmac_hash[dynamic_offset : dynamic_offset + 4]

        code_int = struct.unpack(">I", truncated)[0] & 0x7FFFFFFF
        otp = code_int % (10**digits)

        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(str(otp).zfill(digits), user_code):
            return True

    return False


def generate_otpauth_uri(
    secret: str, username: str, issuer: str = "MFADemo"
) -> str:
    """Generate an otpauth:// URI for QR code encoding.

    This URI format is recognized by Google Authenticator, Microsoft
    Authenticator, Authy, and other TOTP-compatible apps.

    Format: otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}

    Args:
        secret: Base32-encoded shared secret key.
        username: The user's account identifier.
        issuer: The service name (shown in the authenticator app).

    Returns:
        str: The complete otpauth:// URI.
    """
    return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}"
