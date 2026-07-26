from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
    verify_system_token,
)
from app.db import get_db
from app.models import User
from app.ratelimit import RateLimiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Brute-force guard on login: 10 attempts / 60s per client IP (single process).
login_limiter = RateLimiter(max_attempts=10, window_seconds=60.0)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class MeResponse(BaseModel):
    username: str
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not login_limiter.allow(f"login:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts; please wait and try again.",
        )
    user = db.query(User).filter(User.username == body.username).first()
    if (
        not user
        or user.role == "system"
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token({"sub": user.username, "role": user.role})
    return LoginResponse(access_token=token, token_type="bearer", role=user.role)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=user.username, role=user.role)


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="รหัสผ่านปัจจุบันไม่ถูกต้อง",
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="รหัสใหม่ต้องต่างจากรหัสเดิม",
        )
    user.password_hash = hash_password(body.new_password)
    write_audit(
        db,
        who=user.username,
        action="change_password",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True}


@router.get("/system-check")
def system_check(_: None = Depends(verify_system_token)) -> dict:
    return {"ok": True}
