import random
import string
import time
from threading import Lock
from dataclasses import dataclass, field


@dataclass
class Enrollment:
    device_id: str
    token: str
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    refreshed_at: float = field(default_factory=time.time)


class TokenStore:
    def __init__(self, ttl_seconds: int = 300):
        self._store: dict[str, Enrollment] = {}
        self._lock = Lock()
        self._ttl = ttl_seconds

    def _generate_token(self) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def _is_expired(self, entry: Enrollment) -> bool:
        return time.time() - entry.refreshed_at > self._ttl

    def init_enrollment(self, device_id: str) -> dict:
        with self._lock:
            existing = self._store.get(device_id)
            if existing and not self._is_expired(existing):
                return {
                    "device_id": existing.device_id,
                    "token": existing.token,
                    "status": existing.status,
                    "expires_in": int(self._ttl - (time.time() - existing.refreshed_at)),
                }

            token = self._generate_token()
            now = time.time()
            self._store[device_id] = Enrollment(
                device_id=device_id,
                token=token,
                status="pending",
                created_at=now,
                refreshed_at=now,
            )
            return {
                "device_id": device_id,
                "token": token,
                "status": "pending",
                "expires_in": self._ttl,
            }

    def get_token(self, device_id: str) -> dict | None:
        with self._lock:
            entry = self._store.get(device_id)
            if entry is None:
                return None

            if self._is_expired(entry):
                token = self._generate_token()
                entry.token = token
                entry.refreshed_at = time.time()

            return {
                "device_id": entry.device_id,
                "token": entry.token,
                "status": entry.status,
                "expires_in": int(self._ttl - (time.time() - entry.refreshed_at)),
            }

    def approve(self, token: str, device_id: str) -> dict | None:
        with self._lock:
            entry = self._store.get(device_id)
            if entry is None:
                return None

            if self._is_expired(entry):
                return None

            if entry.token != token.upper():
                return None

            entry.status = "approved"
            return {
                "device_id": entry.device_id,
                "status": "approved",
            }

    def get_status(self, device_id: str) -> dict | None:
        with self._lock:
            entry = self._store.get(device_id)
            if entry is None:
                return None
            return {
                "device_id": entry.device_id,
                "status": entry.status,
                "approved": entry.status == "approved",
                "token_expired": self._is_expired(entry),
            }

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [did for did, e in self._store.items() if self._is_expired(e)]
            for did in expired:
                del self._store[did]
            return len(expired)


store = TokenStore(ttl_seconds=300)
