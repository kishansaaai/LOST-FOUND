
import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from ..db import one, scalar, transaction
from ..deps import Principal, current_user, rate_limit
from ..security import (create_access_token, create_refresh_token, decode_token, hash_password,
                        verify_password)
from ..stores import get_redis

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=40)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


def _issue(user_id: int) -> dict:
    access, _, access_ttl = create_access_token(user_id)
    refresh, jti, refresh_ttl = create_refresh_token(user_id)
    try:
        get_redis().setex(f"lf:rt:{jti}", refresh_ttl, str(user_id))  # allow-list of live refresh tokens
    except Exception:                  # session store down: refuse to mint tokens we could not later refresh/revoke
        raise HTTPException(503, "sign-in is temporarily unavailable, please retry shortly") from None
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_in": access_ttl}


@router.post("/register", status_code=201, dependencies=[Depends(rate_limit("register", 10, 3600))])
def register(body: RegisterIn):
    with transaction() as conn:
        if scalar(conn, "SELECT 1 FROM users WHERE lower(email) = lower(:e)", e=body.email):
            raise HTTPException(409, "email already registered")
        u = one(conn, """INSERT INTO users (name, email, password_hash, phone) VALUES (:n, :e, :h, :p)
                         RETURNING user_id AS id, name, email, role::text AS role""",
                n=body.name.strip(), e=str(body.email), h=hash_password(body.password), p=body.phone)
    return {"user": u, **_issue(u["id"])}


@router.post("/login", dependencies=[Depends(rate_limit("login", 10, 60))])
def login(body: LoginIn):
    with transaction() as conn:
        u = one(conn, """SELECT user_id AS id, name, email, role::text AS role, password_hash
                         FROM users WHERE lower(email) = lower(:e)""", e=str(body.email))
    # verify against a dummy hash when the user is unknown so timing does not reveal accounts
    ok = verify_password(body.password, u["password_hash"] if u else hash_password("x"))
    if not u or not ok:
        raise HTTPException(401, "invalid email or password")
    u.pop("password_hash")
    return {"user": u, **_issue(u["id"])}


@router.post("/refresh", dependencies=[Depends(rate_limit("refresh", 30, 60))])
def refresh(body: RefreshIn):
    try:
        claims = decode_token(body.refresh_token, "refresh")
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid refresh token") from None
    try:
        used = get_redis().delete(f"lf:rt:{claims['jti']}")
    except Exception:
        raise HTTPException(503, "sign-in is temporarily unavailable, please retry shortly") from None
    if not used:                                           # single use: already rotated/revoked => reject
        raise HTTPException(401, "refresh token already used or revoked")
    return _issue(int(claims["sub"]))


@router.post("/logout", status_code=204)
def logout(body: RefreshIn | None = None, user: Principal = Depends(current_user)):
    r = get_redis()
    if body:
        try:
            r.delete(f"lf:rt:{decode_token(body.refresh_token, 'refresh')['jti']}")
        except jwt.PyJWTError:
            pass


@router.get("/me")
def me(user: Principal = Depends(current_user)):
    with transaction() as conn:
        return one(conn, "SELECT user_id AS id, name, email, phone, role::text AS role, created_at "
                         "FROM users WHERE user_id = :u", u=user.id)


@router.patch("/me")
def update_me(body: ProfileIn, user: Principal = Depends(current_user)):
    with transaction(user.id) as conn:
        if body.new_password:
            h = scalar(conn, "SELECT password_hash FROM users WHERE user_id = :u", u=user.id)
            if not body.current_password or not verify_password(body.current_password, h):
                raise HTTPException(403, "current password is incorrect")
            conn.execute(text("UPDATE users SET password_hash = :h WHERE user_id = :u"),
                         {"h": hash_password(body.new_password), "u": user.id})
        if body.name is not None or body.phone is not None:
            conn.execute(text(
                "UPDATE users SET name = COALESCE(:n, name), phone = COALESCE(:p, phone) WHERE user_id = :u"),
                {"n": body.name, "p": body.phone, "u": user.id})
        return one(conn, "SELECT user_id AS id, name, email, phone, role::text AS role FROM users WHERE user_id = :u",
                   u=user.id)
