import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from collections.abc import Generator

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

SESSION_COOKIE_NAME = "novora_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_SALT = b"novora-dummy-salt"
_DUMMY_PASSWORD_HASH = hashlib.scrypt(
    b"invalid-password",
    salt=_DUMMY_SALT,
    n=_SCRYPT_N,
    r=_SCRYPT_R,
    p=_SCRYPT_P,
    dklen=_SCRYPT_DKLEN,
    maxmem=64 * 1024 * 1024,
)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str
    full_name: str
    created_at: str
    password_hash: str | None = None


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not _EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address.")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not _EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address.")
        return value


class AuthUserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    created_at: str


class AuthStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        configured_path = db_path or os.getenv("NOVORA_AUTH_DB_PATH")
        self.db_path = str(
            configured_path
            or (Path(__file__).resolve().parents[2] / ".novora-auth.sqlite3")
        )
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires_at
                    ON auth_sessions(expires_at);
                """
            )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_user(
        self,
        email: str,
        full_name: str,
        password_hash: str,
    ) -> AuthenticatedUser | None:
        user_id = f"user_{secrets.token_hex(12)}"
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO auth_users (id, email, full_name, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, email, full_name, password_hash, created_at),
                )
            except sqlite3.IntegrityError:
                return None
        return AuthenticatedUser(user_id, email, full_name, created_at, password_hash)

    def get_user_by_email(self, email: str) -> AuthenticatedUser | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, email, full_name, password_hash, created_at
                FROM auth_users WHERE email = ?
                """,
                (email,),
            ).fetchone()
        if row is None:
            return None
        return AuthenticatedUser(
            id=row["id"],
            email=row["email"],
            full_name=row["full_name"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )

    def create_session(self, user_id: str, token_hash: str, expires_at: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at),
            )

    def get_user_for_session(self, token_hash: str) -> AuthenticatedUser | None:
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.email, u.full_name, u.created_at, s.expires_at
                FROM auth_sessions AS s
                JOIN auth_users AS u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is not None and row["expires_at"] <= now:
                connection.execute(
                    "DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,)
                )
                return None
        if row is None:
            return None
        return AuthenticatedUser(
            id=row["id"],
            email=row["email"],
            full_name=row["full_name"],
            created_at=row["created_at"],
        )

    def delete_session(self, token_hash: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,)
            )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_DUMMY_SALT,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
            maxmem=64 * 1024 * 1024,
        )
        hmac.compare_digest(candidate, _DUMMY_PASSWORD_HASH)
        return False

    algorithm, salt_hex, digest_hex = password_hash.split("$", maxsplit=2)
    if algorithm != "scrypt":
        raise ValueError("Unsupported stored password hash algorithm.")
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    )
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_authenticated_user(
    request: Request,
    auth_store: AuthStore,
) -> AuthenticatedUser:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = (
        auth_store.get_user_for_session(session_token_hash(token))
        if token
        else None
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user
