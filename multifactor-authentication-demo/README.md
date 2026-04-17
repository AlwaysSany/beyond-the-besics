# Multi-Factor Authentication Demo 🔐

A **hands-on mini project** that explains how TOTP-based two-factor authentication works — implementing the same algorithm used by Google Authenticator, from scratch in Python.

> **Part of [beyond-the-besics](../)** — a collection of small projects explaining backend & system design concepts.

---

## 🤔 What Is Multi-Factor Authentication?

Multi-factor authentication (MFA) adds an extra layer of security beyond just a password. Instead of relying on _something you know_ alone, it requires a second factor — typically _something you have_ (like your phone).

The most common approach is **TOTP** (Time-Based One-Time Password), where an authenticator app on your phone generates a short-lived 6-digit code that changes every 30 seconds. This is the system used by **Google Authenticator**, **Microsoft Authenticator**, and **Authy**.

---

## 📖 Theory: How Google Authenticator Works

Google Authenticator is a software-based authenticator developed by Google. It implements multi-step verification services using the **Time-Based One-Time Password (TOTP)** algorithm specified in [RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238), which builds on the **HMAC-Based One-Time Password (HOTP)** algorithm from [RFC 4226](https://datatracker.ietf.org/doc/html/rfc4226).

The service generates a six- to eight-digit one-time password using a shared secret key stored on the device. Users verify identity by providing this code alongside their regular credentials.

### The Core Idea (Mental Model)

```
Both server and your phone share the same secret key.

Both independently compute:

    secret + current time  →  same 6-digit number

If numbers match → you're authenticated.
```

No internet connection is required on the phone — codes are generated entirely offline.

### Phase 1: Initial Setup (Enrollment)

When you enable 2FA on a service (e.g., GitHub, Google, AWS):

| Step | What Happens |
|------|-------------|
| **1.1** | Server generates a random **160-bit secret key**, unique per user. |
| **1.2** | Secret is embedded in an `otpauth://` URI and encoded as a **QR code**. |
| **1.3** | User scans QR with the authenticator app, which stores the secret. |

```
otpauth://totp/MyApp:alice?secret=JBSWY3DPEHPK3PXP&issuer=MyApp
```

> **Important:** The secret key is only transmitted once during setup and never again. Both client and server now share the same secret.

### Phase 2: Code Generation (Every 30 Seconds)

The authenticator app continuously generates new codes using this algorithm:

```
Step 1:  T = floor(current_unix_time / 30)         ← Time counter
Step 2:  HMAC = HMAC-SHA1(secret_key, T)            ← Cryptographic hash
Step 3:  Extract 4-byte chunk (dynamic truncation)  ← Offset from last nibble
Step 4:  OTP = truncated_value mod 10^6             ← 6-digit code
```

In mathematical notation:

```
T    = ⌊ unix_time / 30 ⌋
HMAC = HMAC-SHA1(K, T)
OTP  = DT(HMAC) mod 10⁶
```

Where `DT()` is the dynamic truncation function defined in RFC 4226.

### Phase 3: Login Flow

```
┌──────────┐         ┌──────────┐         ┌──────────┐
│  User    │         │  Server  │         │  Phone   │
└────┬─────┘         └────┬─────┘         └────┬─────┘
     │  username+pwd      │                    │
     │───────────────────>│                    │
     │                    │                    │
     │  "Enter OTP"       │                    │
     │<───────────────────│                    │
     │                    │                    │
     │  reads code        │                    │
     │<────────────────────────────────────────│
     │                    │                    │
     │  sends OTP code    │                    │
     │───────────────────>│                    │
     │                    │                    │
     │                    │ recomputes OTP     │
     │                    │ using stored       │
     │                    │ secret + time      │
     │                    │                    │
     │  ✅ authenticated  │                    │
     │<───────────────────│                    │
```

### Phase 4: Server Verification

The server verifies by:

1. **Recomputing** the OTP using the stored secret and current time
2. **Checking a time window** — typically `T-1`, `T`, `T+1` — to handle small clock drift
3. **Comparing codes** using constant-time comparison (prevents timing attacks)

### Why It's Secure

| Property | Explanation |
|----------|-------------|
| **No Shared Transmission** | Secret is only exchanged once (during setup via QR). |
| **Time-Based Expiry** | Codes expire every 30 seconds. |
| **Replay Protection** | Old codes become useless quickly. |
| **Offline Generation** | No internet required for the app — works in airplane mode. |
| **Cryptographic Strength** | Uses HMAC-SHA1, a well-studied cryptographic primitive. |

### Known Limitations

| Risk | Description |
|------|-------------|
| **Phishing** | If an attacker tricks a user into entering an OTP on a fake site, they can use it immediately in the valid time window. |
| **No Device Binding** | Codes are not tied to a specific device or session. |
| **Backup Risk** | Losing the phone (or factory reset) means losing access unless backup codes exist. |
| **Clock Drift** | Significant time differences between client and server can cause verification failures. |

> **Modern alternatives** like **WebAuthn / Passkeys** address some of these limitations by binding authentication to specific devices and using public-key cryptography instead of shared secrets.

### Underlying Standards

| Standard | Description |
|----------|-------------|
| [RFC 4226](https://datatracker.ietf.org/doc/html/rfc4226) | **HOTP** — HMAC-Based One-Time Password (counter-based) |
| [RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238) | **TOTP** — Time-Based One-Time Password (builds on HOTP) |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) package manager

### Run the Interactive CLI Demo

```bash
# Navigate to this project
cd multifactor-authentication-demo

# Run the step-by-step TOTP demo (recommended first!)
uv run demo.py
```

This walks you through each step of the TOTP algorithm interactively and lets you verify codes with a real authenticator app.

### Run the FastAPI Server

```bash
# Install dependencies
uv sync

# Start the server
uv run uvicorn main:app --reload

# Open the interactive API docs
# → http://127.0.0.1:8000/docs
```

---

## 📁 Project Structure

```
multifactor-authentication-demo/
├── main.py            # FastAPI app — complete 2FA REST API
├── security.py        # Core TOTP engine (RFC 6238 implementation)
├── models.py          # Pydantic request/response schemas
├── database.py        # In-memory user store (demo only)
├── demo.py            # Interactive CLI walkthrough of the TOTP algorithm
├── details.txt        # Raw research notes and reference material
├── pyproject.toml     # Project config & dependencies
└── README.md          # You are here
```

---

## 🔧 How the Code Maps to the Algorithm

### `security.py` — The TOTP Engine

| Function | RFC Step | What It Does |
|----------|----------|-------------|
| `generate_secret()` | Setup | Creates a 160-bit random Base32 key |
| `base32_decode()` | Setup | Decodes Base32 secret → raw bytes |
| `int_to_bytes()` | §5.2 | Converts time counter → 8-byte big-endian |
| `generate_totp()` | §5.3-5.4 | Full OTP generation: HMAC → truncate → mod |
| `verify_totp()` | §5.4 | Checks OTP across time window (T±1) |
| `generate_otpauth_uri()` | Enrollment | Creates scannable `otpauth://` URI |

### `main.py` — The FastAPI Endpoints

| Endpoint | Purpose | Phase |
|----------|---------|-------|
| `POST /register` | Create user + generate secret | Registration |
| `GET /enable-2fa/{username}` | Return QR code image | Enrollment |
| `POST /verify-2fa` | Confirm OTP → activate 2FA | Enrollment |
| `POST /login` | Password verification | Login Step 1 |
| `POST /login-2fa` | OTP verification | Login Step 2 |

---

## 🧪 Try the Full Flow

### Using the Swagger UI (`/docs`)

**1. Register a user:**
```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
```

**2. Get the QR code:**
Open `http://localhost:8000/enable-2fa/alice` in your browser — scan with Google Authenticator.

**3. Verify OTP to enable 2FA:**
```bash
curl -X POST http://localhost:8000/verify-2fa \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "otp": "482193"}'
```

**4. Login (will now require OTP):**
```bash
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
# Response: {"message": "Enter OTP", "2fa_required": true}
```

**5. Complete login with OTP:**
```bash
curl -X POST http://localhost:8000/login-2fa \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "otp": "INSERT_CODE_HERE"}'
```

---

## 🔒 Production Considerations

This is an educational demo. In a production system, you'd want:

| Area | Demo | Production |
|------|------|------------|
| **Database** | In-memory dict | PostgreSQL with encrypted secret storage |
| **Password Hashing** | SHA-256 | bcrypt / argon2 |
| **Sessions** | None | JWT access + refresh tokens |
| **Rate Limiting** | None | Prevent OTP brute force (max 5 attempts) |
| **Backup Codes** | None | One-time recovery codes |
| **Secret Encryption** | Plaintext | AES-256 / KMS at rest |
| **HTTPS** | None | Required for all endpoints |

---

## 💡 Key Concepts

| Concept | Explanation |
|---------|-------------|
| **TOTP** | Time-Based One-Time Password — codes change every 30 seconds |
| **HOTP** | HMAC-Based OTP — counter-based, the foundation TOTP builds on |
| **Shared Secret** | A key known to both server and authenticator app |
| **Time Counter (T)** | `floor(unix_time / 30)` — both sides compute independently |
| **Dynamic Truncation** | Extracting a 4-byte chunk from the HMAC hash |
| **Time Window** | Checking T-1, T, T+1 to handle clock drift (~90s validity) |
| **QR Enrollment** | `otpauth://` URI encoded as QR for easy setup |
| **Constant-Time Compare** | `hmac.compare_digest()` prevents timing side-channel attacks |

---

## 🆚 How This Compares to Real Systems

| Feature | This Demo | Google/GitHub 2FA | Enterprise IAM |
|---------|-----------|-------------------|----------------|
| TOTP generation | ✅ | ✅ | ✅ |
| QR onboarding | ✅ | ✅ | ✅ |
| Time window tolerance | ✅ | ✅ | ✅ |
| Backup codes | ❌ | ✅ | ✅ |
| Device binding | ❌ | ❌ | ✅ (WebAuthn) |
| Push notifications | ❌ | ✅ | ✅ |
| Risk-based MFA | ❌ | ✅ | ✅ |

This demo intentionally omits advanced features to keep the **core TOTP algorithm crystal clear**.
