"""
Authentication for the Strop API.

* One password for the controller, stored only as a salted hash in
  config.json ("auth.password_hash"); set it with scripts/set_password.py.
* After login the client gets a signed, expiring bearer token
  (itsdangerous, ships with Flask). Tokens carry a version number: changing
  the password bumps it and invalidates every existing session.
* Fails closed: with no password configured every protected endpoint
  answers 401 and login explains how to set one.
* Login attempts are rate limited per client; X-Forwarded-For is trusted
  only from the proxies listed in "auth.trusted_proxies" (Traefik).
"""
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

TOKEN_SALT = 'strop-auth'
DEFAULT_TOKEN_DAYS = 30
MIN_PASSWORD_LENGTH = 8
MAX_FAILURES = 5           # per client within the window
MAX_GLOBAL_FAILURES = 30   # all clients within the window
FAILURE_WINDOW = 15 * 60   # seconds


class AuthService:
    def __init__(self, config_service):
        self.config_service = config_service
        self._mtime = None
        self._lock = threading.Lock()
        self._failures = defaultdict(deque)
        self._global_failures = deque()
        self._reload(force=True)

    # ------------------------------------------------------------------ config
    def _reload(self, force: bool = False) -> None:
        """Re-read config.json when it changed (e.g. after set_password.py)."""
        path = self.config_service.config_path
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if not force and mtime == self._mtime:
            return
        if not force:
            try:
                self.config_service.config = self.config_service._load_config()
            except Exception as e:  # e.g. file being rewritten right now
                logger.warning("Could not reload config, keeping previous auth settings: %s", e)
                return
        self._mtime = mtime
        auth = self.config_service.get('auth', {}) or {}
        if not auth.get('secret'):
            self.config_service.update('auth.secret', secrets.token_hex(32))
            self._mtime = os.path.getmtime(path)
            auth = self.config_service.get('auth', {})
        self.secret = auth['secret']
        self.password_hash = auth.get('password_hash') or ''
        self.token_version = int(auth.get('token_version', 1))
        self.token_days = int(auth.get('token_days', DEFAULT_TOKEN_DAYS))
        self.trusted_proxies = set(auth.get('trusted_proxies', []))
        self._serializer = URLSafeTimedSerializer(self.secret, salt=TOKEN_SALT)

    def is_configured(self) -> bool:
        self._reload()
        return bool(self.password_hash)

    # ------------------------------------------------------------------ password
    def check_password(self, password: str) -> bool:
        self._reload()
        if not self.password_hash or not password:
            return False
        return check_password_hash(self.password_hash, password)

    def set_password(self, password: str) -> None:
        if len(password or '') < MIN_PASSWORD_LENGTH:
            raise ValueError(f'Password must have at least {MIN_PASSWORD_LENGTH} characters')
        self._reload()
        cfg = self.config_service
        cfg.update('auth.password_hash', generate_password_hash(password))
        cfg.update('auth.token_version', self.token_version + 1)  # log out all sessions
        self._reload(force=True)

    # ------------------------------------------------------------------ tokens
    @property
    def token_max_age(self) -> int:
        return self.token_days * 86400

    def issue_token(self) -> str:
        self._reload()
        return self._serializer.dumps({'v': self.token_version})

    def verify_token(self, token: Optional[str]) -> bool:
        if not token:
            return False
        self._reload()
        if not self.password_hash:
            return False
        try:
            data = self._serializer.loads(token, max_age=self.token_max_age)
        except (SignatureExpired, BadSignature):
            return False
        return isinstance(data, dict) and data.get('v') == self.token_version

    # ------------------------------------------------------------------ rate limit
    def client_key(self, remote_addr: str, forwarded_for: Optional[str]) -> str:
        if forwarded_for and remote_addr in self.trusted_proxies:
            return forwarded_for.split(',')[0].strip()
        return remote_addr or 'unknown'

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] > FAILURE_WINDOW:
            q.popleft()

    def retry_after(self, key: str) -> int:
        """Seconds to wait before another attempt is allowed (0 = allowed)."""
        now = time.time()
        with self._lock:
            q = self._failures[key]
            self._prune(q, now)
            self._prune(self._global_failures, now)
            if len(q) >= MAX_FAILURES:
                return int(FAILURE_WINDOW - (now - q[0])) + 1
            if len(self._global_failures) >= MAX_GLOBAL_FAILURES:
                return int(FAILURE_WINDOW - (now - self._global_failures[0])) + 1
            return 0

    def record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            self._failures[key].append(now)
            self._global_failures.append(now)
        logger.warning("Failed login attempt from %s", key)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
