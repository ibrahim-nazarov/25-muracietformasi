"""Parol hash-ləri. Terminalda: python auth.py "parol" """
import hashlib
import hmac
import secrets
import sys

ITERATIONS = 200_000


def make_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_hash(password, stored):
    try:
        _, salt, expected = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected)


if __name__ == "__main__":
    print(make_hash(sys.argv[1]))
