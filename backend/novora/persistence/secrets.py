import base64
import hashlib
import os
from cryptography.fernet import Fernet

class SecretManager:
    """Manages secure credential masking, hashing, and encryption using AES (Fernet)."""

    @staticmethod
    def _get_fernet() -> Fernet:
        secret = os.getenv("NOVORA_SECRET_KEY") or os.getenv("NOVORA_SECRET_SALT", "novora_default_encryption_key_2026")
        # Derive a stable 32-byte URL-safe base64 key
        derived = hashlib.sha256(secret.encode("utf-8")).digest()
        key_b64 = base64.urlsafe_b64encode(derived)
        return Fernet(key_b64)

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

    @classmethod
    def encode_credential(cls, secret: str) -> str:
        """Encrypt secret using Fernet (AES-128-CBC with HMAC-SHA256)."""
        if not secret:
            return ""
        f = cls._get_fernet()
        return f.encrypt(secret.encode("utf-8")).decode("ascii")

    @classmethod
    def decode_credential(cls, encoded: str) -> str:
        """Decrypt secret using Fernet, with backwards-compatible fallback to legacy XOR."""
        if not encoded:
            return ""
        f = cls._get_fernet()
        try:
            return f.decrypt(encoded.encode("ascii")).decode("utf-8")
        except Exception:
            try:
                key = os.getenv("NOVORA_SECRET_SALT", "novora_key").encode("utf-8")
                raw = base64.b64decode(encoded.encode("ascii"))
                xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
                return xored.decode("utf-8")
            except Exception:
                return encoded
