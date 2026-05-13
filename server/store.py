import random
import threading
import time
import logging

logger = logging.getLogger(__name__)

TOKEN_TTL = 300
PURGE_INTERVAL = 30


class TokenStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._store: dict[str, dict] = {}
        self._purge_thread = threading.Thread(target=self._purge_loop, daemon=True)
        self._purge_thread.start()

    def _generate_token(self) -> str:
        return "".join(random.choices("0123456789", k=6))

    def _purge_loop(self):
        while True:
            time.sleep(PURGE_INTERVAL)
            with self._lock:
                now = time.time()
                expired = [
                    did for did, entry in self._store.items()
                    if entry["expires_at"] < now
                ]
                for did in expired:
                    del self._store[did]
                if expired:
                    logger.info(f"Purged {len(expired)} expired token(s)")

    def get_or_create_token(self, device_id: str) -> str:
        with self._lock:
            now = time.time()
            entry = self._store.get(device_id)

            if entry is None or entry["expires_at"] < now:
                token = self._generate_token()
                self._store[device_id] = {
                    "token": token,
                    "approved": False,
                    "expires_at": now + TOKEN_TTL,
                }
                return token

            return entry["token"]

    def approve(self, token: str, device_id: str) -> bool:
        with self._lock:
            entry = self._store.get(device_id)
            if entry is None:
                return False
            if entry["expires_at"] < time.time():
                return False
            if entry["token"] != token:
                return False

            entry["approved"] = True
            return True

    def get_status(self, device_id: str) -> bool:
        with self._lock:
            entry = self._store.get(device_id)
            if entry is None:
                return False
            return entry["approved"]


store = TokenStore()
