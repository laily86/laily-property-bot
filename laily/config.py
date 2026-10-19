import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    token: str
    user_id: int
    key: bytes
    data_dir: Path

    @classmethod
    def load(cls):
        load_dotenv()
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        raw_id = os.environ.get("AUTHORIZED_TELEGRAM_USER_ID", "")
        key = os.environ.get("DATA_ENCRYPTION_KEY", "").encode()
        if not token or not raw_id.isdigit() or int(raw_id) <= 0 or not key:
            raise ValueError("Tetapkan token, ID pengguna angka dan kunci penyulitan dalam .env.")
        Fernet(key)  # Validate before touching storage or contacting Telegram.
        return cls(token, int(raw_id), key, Path(os.environ.get("DATA_DIR", "./data")))
