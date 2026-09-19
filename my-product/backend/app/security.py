from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .config import get_settings
from .database import get_connection
from .errors import BusinessError


password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, password_digest: str) -> bool:
    try:
        return password_hash.verify(password, password_digest)
    except Exception:
        return False


def create_access_token(user: dict[str, Any]) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    connection: Connection = Depends(get_connection),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise BusinessError(1002, "未登录或 Token 已失效", status_code=401)
    try:
        payload = jwt.decode(credentials.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise BusinessError(1002, "未登录或 Token 已失效", status_code=401) from exc

    row = connection.execute(
        text("SELECT id, username, real_name, role, data_scope, status FROM sys_user WHERE id=:id"),
        {"id": user_id},
    ).mappings().first()
    if row is None or row["status"] != "active":
        raise BusinessError(1002, "账号不存在、已禁用或 Token 已失效", status_code=401)
    return dict(row)


def require_roles(*roles: str):
    def dependency(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise BusinessError(1003, "无权限执行此操作", status_code=403)
        return user
    return dependency
