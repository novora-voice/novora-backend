import base64
import hashlib
import os

class SecretManager:
    """Manages secure credential masking and server-side obfuscation."""

    @staticmethod
    def mask_secret(secret: str) -> str:
        if not secret:
            return ""
        s = secret.strip()
        if len(s) <= 6:
            return "******"
        return f"{s[:3]}...{s[-4:]}"

    @staticmethod
    def hash_token(secret: str) -> str:
        salt = os.getenv("NOVORA_SECRET_SALT", "novora_default_salt_2026")
        return hashlib.sha256(f"{secret}:{salt}".encode("utf-8")).hexdigest()

    @staticmethod
    def encode_credential(secret: str) -> str:
        # Reversible obfuscation for safe local storage
        key = os.getenv("NOVORA_SECRET_SALT", "novora_key").encode("utf-8")
        raw = secret.encode("utf-8")
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
        return base64.b64encode(xored).decode("ascii")

    @staticmethod
    def decode_credential(encoded: str) -> str:
        key = os.getenv("NOVORA_SECRET_SALT", "novora_key").encode("utf-8")
        raw = base64.b64decode(encoded.encode("ascii"))
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
        return xored.decode("utf-8")
