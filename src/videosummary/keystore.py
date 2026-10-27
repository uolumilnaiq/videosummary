import json
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet


class Keystore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._dir = base_dir or Path.home() / ".ghdigest"
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self._master_key_path = self._dir / "master.key"
        self._keystore_path = self._dir / "keystore.enc"

    def _get_or_create_fernet(self) -> Fernet:
        if not self._master_key_path.exists():
            key = Fernet.generate_key()
            self._master_key_path.write_bytes(key)
            os.chmod(self._master_key_path, stat.S_IRUSR | stat.S_IWUSR)
        os.chmod(self._master_key_path, stat.S_IRUSR | stat.S_IWUSR)
        key = self._master_key_path.read_bytes()
        return Fernet(key)

    def _load_store(self) -> dict[str, str]:
        if not self._keystore_path.exists():
            return {}
        fernet = self._get_or_create_fernet()
        try:
            raw = fernet.decrypt(self._keystore_path.read_bytes())
            return json.loads(raw.decode())
        except Exception as exc:
            raise ValueError("Failed to decrypt keystore; it may be corrupted.") from exc

    def _save_store(self, store: dict[str, str]) -> None:
        fernet = self._get_or_create_fernet()
        encrypted = fernet.encrypt(json.dumps(store).encode())
        self._keystore_path.write_bytes(encrypted)

    def store(self, key: str, value: str) -> None:
        store = self._load_store()
        store[key] = value
        self._save_store(store)
        # Python str is immutable; in-memory zeroing is not reliably possible.
        # The caller should minimize the lifetime of the plaintext value.

    def load(self, key: str) -> str | None:
        store = self._load_store()
        return store.get(key)
