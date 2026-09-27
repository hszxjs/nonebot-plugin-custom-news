"""WebUI 认证：HMAC 签名 Token + 慢哈希口令 + 登录失败退避。

- 口令：scrypt（stdlib，无新依赖）；旧的**无盐 SHA-256** 会在首次成功登录时透明重写
- Token：HMAC-SHA256，载荷含 jti/exp；改密码时轮换 secret，旧 secret 保留 1 小时
  宽限期，因此正在使用的会话不会被立刻踢掉
- 登录失败：同一用户名连续 5 次失败锁 5 分钟（进程内计数，重启清零）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..store import Store, get_store

_TOKEN_TTL = 7 * 24 * 3600  # 7 天
_SECRET_GRACE_SECONDS = 3600  # 改密码后旧 Token 的宽限期
_MAX_LOGIN_FAILURES = 5
_LOCK_SECONDS = 300
_bearer = HTTPBearer(auto_error=False)

#: 进程内登录失败计数（单进程部署足够拦住在线爆破）
_failures: dict[str, tuple[int, float]] = {}


# ---------------------------------------------------------------- 口令


def _hash_password(password: str) -> str:
    """scrypt 哈希，参数随哈希一起存，便于日后调参。"""
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"


def _verify_hash(stored: str, password: str) -> bool:
    if stored.startswith("scrypt$"):
        try:
            _, n, r, p, salt_hex, digest_hex = stored.split("$")
            got = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(digest_hex) // 2,
            )
        except Exception:
            return False
        return hmac.compare_digest(got.hex(), digest_hex)
    # 兼容旧的无盐 SHA-256（登录成功后由 verify_password 重写为 scrypt）
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored)


def verify_password(store: Store, username: str, password: str) -> bool:
    auth = store.config.webui
    if not hmac.compare_digest(username, auth.username):
        return False
    if not _verify_hash(auth.password_sha, password):
        return False
    if not auth.password_sha.startswith("scrypt$"):
        auth.password_sha = _hash_password(password)
        store.save_sync()
    return True


def change_password(store: Store, new_password: str) -> None:
    if not (6 <= len(new_password) <= 64):
        raise ValueError("密码长度需在 6~64 位之间")
    auth = store.config.webui
    # 轮换 secret：旧 Token 最多再活 grace 秒后全部失效（原先改密码不轮换，
    # 泄露出去的 Token 可以一直用到 7 天过期，且无法撤销）
    auth.secret_prev = auth.secret
    auth.secret_rotated_at = time.time()
    auth.secret = secrets.token_hex(32)
    auth.password_sha = _hash_password(new_password)
    store.save_sync()


def verify_login_allowed(username: str) -> None:
    _, until = _failures.get(username, (0, 0.0))
    if until > time.time():
        raise HTTPException(
            status_code=429,
            detail=f"登录失败次数过多，请 {int(until - time.time())} 秒后再试",
        )


def note_login_failure(username: str) -> None:
    count, _ = _failures.get(username, (0, 0.0))
    count += 1
    until = time.time() + _LOCK_SECONDS if count >= _MAX_LOGIN_FAILURES else 0.0
    _failures[username] = (count, until)


def note_login_success(username: str) -> None:
    _failures.pop(username, None)


# ---------------------------------------------------------------- Token


def _sign(secret: str, b64: str) -> str:
    return hmac.new(secret.encode(), b64.encode(), hashlib.sha256).hexdigest()


def issue_token(store: Store, username: str) -> str:
    payload = json.dumps(
        {
            "u": username,
            "exp": int(time.time()) + _TOKEN_TTL,
            "jti": secrets.token_urlsafe(8),  # 同秒登录不再产出完全相同的 Token
        },
        separators=(",", ":"),
    )
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode()
    return f"{b64}.{_sign(store.config.webui.secret, b64)}"


def _check_token(store: Store, token: str) -> bool:
    try:
        b64, sig = token.split(".", 1)
        auth = store.config.webui
        candidates = [auth.secret]
        if auth.secret_prev and (
            time.time() - auth.secret_rotated_at < _SECRET_GRACE_SECONDS
        ):
            candidates.append(auth.secret_prev)
        if not any(hmac.compare_digest(sig, _sign(s, b64)) for s in candidates):
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
