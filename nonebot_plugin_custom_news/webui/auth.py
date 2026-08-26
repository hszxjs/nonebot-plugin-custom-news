"""WebUI 认证：HMAC 签名 Token（无额外依赖）。"""

import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..store import Store, get_store

_TOKEN_TTL = 7 * 24 * 3600  # 7 天
_bearer = HTTPBearer(auto_error=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_password(store: Store, username: str, password: str) -> bool:
    auth = store.config.webui
    return hmac.compare_digest(username, auth.username) and hmac.compare_digest(
        _sha256(password), auth.password_sha
    )


def change_password(store: Store, new_password: str) -> None:
    if not (6 <= len(new_password) <= 64):
        raise ValueError("密码长度需在 6~64 位之间")
    store.config.webui.password_sha = _sha256(new_password)
    store.save_sync()


def issue_token(store: Store, username: str) -> str:
    payload = json.dumps(
        {"u": username, "exp": int(time.time()) + _TOKEN_TTL},
        separators=(",", ":"),
    )
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode()
    sig = hmac.new(
        store.config.webui.secret.encode(), b64.encode(), hashlib.sha256
    ).hexdigest()
    return f"{b64}.{sig}"


def _check_token(store: Store, token: str) -> bool:
    try:
        b64, sig = token.split(".", 1)
        expect = hmac.new(
            store.config.webui.secret.encode(), b64.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return False
        payload = json.loads(base64.urlsafe_b64decode(b64))
        return payload.get("exp", 0) > time.time()
    except Exception:
        return False


async def require_auth(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Store:
    store = get_store()
    if cred is None or not _check_token(store, cred.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或 Token 已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return store
