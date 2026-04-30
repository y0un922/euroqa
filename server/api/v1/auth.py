"""Simple shared-password authentication."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from server.config import ServerConfig
from server.deps import get_config

router = APIRouter()


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


class AuthStatusResponse(BaseModel):
    required: bool


# ---------------------------------------------------------------------------
# Token sign / verify
# ---------------------------------------------------------------------------

def _encode_payload(data: dict[str, int]) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode_payload(encoded: str) -> dict[str, int]:
    padded = encoded + "=" * (-len(encoded) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded))
    if not isinstance(data, dict):
        raise ValueError("payload must be an object")
    return data


def _hmac_signature(payload_str: str, secret: str) -> str:
    return hmac.new(
        secret.encode(), payload_str.encode(), hashlib.sha256
    ).hexdigest()


def sign_token(config: ServerConfig) -> str:
    now = int(time.time())
    payload = _encode_payload({"iat": now, "exp": now + config.auth_token_ttl_seconds})
    return f"{payload}.{_hmac_signature(payload, config.auth_secret_key)}"


def verify_token(token: str, config: ServerConfig) -> bool:
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False

    payload_str, signature = parts
    expected = _hmac_signature(payload_str, config.auth_secret_key)
    if not secrets.compare_digest(signature, expected):
        return False

    try:
        data = _decode_payload(payload_str)
        return int(data["exp"]) >= int(time.time())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(config: ServerConfig = Depends(get_config)) -> AuthStatusResponse:
    return AuthStatusResponse(required=bool(config.access_password))


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    config: ServerConfig = Depends(get_config),
) -> LoginResponse:
    if not config.access_password:
        return LoginResponse(token=sign_token(config))

    if not secrets.compare_digest(body.password, config.access_password):
        raise HTTPException(status_code=401, detail="密码不正确")

    return LoginResponse(token=sign_token(config))


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def require_auth(
    authorization: Annotated[str | None, Header()] = None,
    token: Annotated[str | None, Query(alias="token")] = None,
    config: ServerConfig = Depends(get_config),
) -> None:
    if not config.access_password:
        return

    raw_token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_token(raw_token, config):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
