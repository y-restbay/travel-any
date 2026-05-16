import base64
import hashlib
import hmac
import json
import time
from typing import Any
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings


TOKEN_TTL_SECONDS = 60 * 60 * 12
security = HTTPBearer(auto_error=False)


def _secret() -> str:
    settings = get_settings()
    return settings.admin_token_secret or settings.admin_password


def _sign(payload: str) -> str:
    return hmac.new(_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _b64encode(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def create_admin_token(username: str) -> str:
    payload = _b64encode({"sub": username, "iat": int(time.time())})
    return f"{payload}.{_sign(payload)}"


def verify_admin_token(token: str) -> str:
    try:
        payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token") from exc

    if not hmac.compare_digest(_sign(payload), signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")

    try:
        data = _b64decode(payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token") from exc

    issued_at = int(data.get("iat") or 0)
    if issued_at <= 0 or time.time() - issued_at > TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token expired")

    username = str(data.get("sub") or "")
    if username != get_settings().admin_username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
    return username


def require_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authorization required")
    return verify_admin_token(credentials.credentials)
