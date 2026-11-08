from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional


def password_digest(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1).hex()


@dataclass
class Session:
    username: str
    expires_at: float


class AuthManager:
    def __init__(self, password: str, ttl_seconds: int):
        self._salt = secrets.token_bytes(16)
        self._password_digest = password_digest(password, self._salt)
        self._ttl = ttl_seconds
        self._sessions: Dict[str, Session] = {}
        self._failures: Dict[str, list] = {}

    def verify_password(self, password: str) -> bool:
        candidate = password_digest(password, self._salt)
        return hmac.compare_digest(candidate, self._password_digest)

    def create_session(self, username: str = "admin") -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = Session(username=username, expires_at=time.time() + self._ttl)
        return token

    def user_for_token(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        session = self._sessions.get(token)
        if not session:
            return None
        if session.expires_at < time.time():
            self._sessions.pop(token, None)
            return None
        return session.username

    def revoke(self, token: Optional[str]) -> None:
        if token:
            self._sessions.pop(token, None)

    def login_allowed(self, key: str, limit: int = 5, window_seconds: int = 60) -> bool:
        now = time.time()
        attempts = [stamp for stamp in self._failures.get(key, []) if now - stamp < window_seconds]
        self._failures[key] = attempts
        return len(attempts) < limit

    def record_login_failure(self, key: str) -> None:
        self._failures.setdefault(key, []).append(time.time())

    def clear_login_failures(self, key: str) -> None:
        self._failures.pop(key, None)

