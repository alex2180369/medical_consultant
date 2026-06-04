"""Password hashing helpers."""

import hashlib
import secrets

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, digest = password_hash.split("$", 1)
    except ValueError:
        return False

    computed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return secrets.compare_digest(computed.hex(), digest)
