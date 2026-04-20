"""
Interactive CLI demo of the TOTP algorithm.

Run this standalone to see how TOTP works step-by-step,
without needing to start the FastAPI server.

Usage:
    uv run demo.py
"""

import time

from security import base32_decode, generate_secret, generate_totp, verify_totp


def print_header(text: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def main() -> None:
    """Run the interactive TOTP demo."""

    print_header("🔐 TOTP (Time-Based One-Time Password) — Live Demo")
    print()
    print("  This demo implements the same algorithm used by:")
    print("  • Google Authenticator")
    print("  • Microsoft Authenticator")
    print("  • Authy")
    print()
    print("  Standard: RFC 6238 (TOTP) built on RFC 4226 (HOTP)")
    print()

    # ── Step 1: Generate a shared secret ──
    print_header("Step 1: Generate Shared Secret")

    secret = generate_secret()
    raw_bytes = base32_decode(secret)

    print(f"  Base32 Secret : {secret}")
    print(f"  Raw Key Bytes : {raw_bytes.hex()}")
    print(f"  Key Length    : {len(raw_bytes)} bytes ({len(raw_bytes) * 8} bits)")
    print()
    print("  ℹ️  This secret is shared once during setup (via QR code)")
    print("     and never transmitted again.")

    # ── Step 2: Show current time slice ──
    print_header("Step 2: Compute Time Counter")

    current_time = int(time.time())
    interval = 30
    counter = current_time // interval
    remaining = interval - (current_time % interval)

    print(f"  Current Unix Time : {current_time}")
    print(f"  Interval          : {interval} seconds")
    print(f"  Time Counter (T)  : {counter}")
    print(f"  Seconds Remaining : {remaining}s")
    print()
    print("  ℹ️  T = floor(unix_time / 30)")
    print("     Both client and server compute the same T independently.")

    # ── Step 3: Generate OTP ──
    print_header("Step 3: Generate OTP")

    otp = generate_totp(secret)

    print(f"  Generated OTP : {otp}")
    print()
    print("  Algorithm:")
    print("    1. HMAC-SHA1(secret_key, time_counter)")
    print("    2. Dynamic truncation → extract 4-byte chunk")
    print("    3. Modulo 10^6 → 6-digit code")
    print("    4. Zero-pad if needed")

    # ── Step 4: Verify OTP ──
    print_header("Step 4: Verify OTP")

    is_valid = verify_totp(secret, otp)
    print(f"  Code '{otp}' valid? → {'✅ Yes' if is_valid else '❌ No'}")
    print()
    print("  The server checks T-1, T, and T+1 to handle clock drift.")
    print("  This means each code is valid for ~90 seconds total.")

    # ── Step 5: Interactive verification ──
    print_header("Step 5: Try It Yourself!")
    print()
    print(f"  Your secret is: {secret}")
    print()
    print("  You can add this to Google Authenticator manually:")
    print("    1. Open Google Authenticator")
    print("    2. Tap '+' → 'Enter a setup key'")
    print(f"    3. Enter key: {secret}")
    print("    4. Set type: Time based")
    print()

    while True:
        user_input = input("  Enter OTP (or 'q' to quit): ").strip()

        if user_input.lower() == "q":
            break

        if verify_totp(secret, user_input):
            print("  ✅ OTP is valid!")
        else:
            current_otp = generate_totp(secret)
            print(f"  ❌ Invalid OTP. Current code is: {current_otp}")

        print()

    print_header("Done! 🎉")
    print("  You've seen how TOTP works under the hood.")
    print("  Check the README for the full theory and FastAPI integration.")
    print()


if __name__ == "__main__":
    main()
