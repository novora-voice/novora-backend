import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from novora.api.auth_utils import (
    Base,
    ConfigurationOrm,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserOrm,
    UserResponse,
    create_access_token,
    decode_token,
    get_db,
    hash_password,
    init_db,
    verify_password,
)

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserOrm:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = decode_token(credentials.credentials)
    user = db.query(UserOrm).filter(UserOrm.id == user_id, UserOrm.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or has been deactivated.",
        )
    return user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(UserOrm).filter(UserOrm.email == req.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with the email address '{req.email}' already exists.",
        )
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters long.",
        )
    hashed = hash_password(req.password)
    user = UserOrm(
        id=str(uuid.uuid4()),
        email=req.email,
        full_name=req.full_name.strip(),
        hashed_password=hashed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at.isoformat(),
        ),
    )

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(UserOrm).filter(UserOrm.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated.",
        )

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at.isoformat(),
        ),
    )

@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserOrm = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        created_at=current_user.created_at.isoformat(),
    )

@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(_: UserOrm = Depends(get_current_user)):
    return {"status": "logged_out", "message": "You have been signed out successfully."}
