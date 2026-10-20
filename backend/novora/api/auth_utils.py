import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.pool import StaticPool
import bcrypt

try:
    from passlib.context import CryptContext
    _passlib_context: Optional[CryptContext] = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception:
    _passlib_context = None

try:
    from jose import JWTError, jwt
except ImportError as e:
    raise RuntimeError("python-jose[cryptography] is required.") from e

DATABASE_URL: str = os.environ.get(
    "NOVORA_DATABASE_URL",
    "postgresql+psycopg://postgres:Chibueze2007@127.0.0.1:5432/novora",
)
SECRET_KEY: str = os.environ.get("NOVORA_JWT_SECRET", "novora-super-secret-key-CHANGE-IN-PRODUCTION")
ALGORITHM = "HS256"
AUTH_TOKEN_EXPIRE_HOURS = 12

def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8")):
            return True
    except Exception:
        pass
    if _passlib_context is not None:
        try:
            return _passlib_context.verify(plain_password, hashed_password)
        except Exception:
            pass
    return False

if DATABASE_URL.startswith("sqlite"):
    sqlite_options = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in DATABASE_URL or DATABASE_URL == "sqlite://":
        sqlite_options["poolclass"] = StaticPool
    engine = create_engine(DATABASE_URL, **sqlite_options)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class UserOrm(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(320), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    configurations = relationship("ConfigurationOrm", back_populates="user", cascade="all, delete-orphan")

class ConfigurationOrm(Base):
    __tablename__ = "configurations"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_config_user_key"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    user = relationship("UserOrm", back_populates="configurations")

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(description="Valid email address")
    password: str = Field(min_length=8, description="Minimum 8 characters")

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    created_at: str
    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = AUTH_TOKEN_EXPIRE_HOURS * 3600
    user: UserResponse

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=AUTH_TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc), "type": "access"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing subject claim.")
        return user_id
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid token.") from exc
