import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from .listings import extract, fingerprint, property_signature

MAX_PHOTO_BYTES = 10 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory, key):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        self.cipher = Fernet(key)
        self.path = directory / "drafts.sqlite3"
        # No raw listing, source, captions, photos, tokens or agent data in SQLite.
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS listings (id TEXT PRIMARY KEY, payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, created TEXT NOT NULL,
                    event TEXT NOT NULL, listing_id TEXT, detail BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY);
            ''')
            # Fail closed before any new writes if the supplied key cannot open existing data.
            sample = db.execute("SELECT payload FROM listings LIMIT 1").fetchone()
            if sample is None:
                sample = db.execute("SELECT detail FROM audit LIMIT 1").fetchone()
            if sample:
                self.decrypt(sample[0])
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def encrypt(self, obj):
        return self.cipher.encrypt(json.dumps(obj, ensure_ascii=False).encode())

    def decrypt(self, data):
        return json.loads(self.cipher.decrypt(data))

    def all(self):
        with self.db() as db:
            return [self.decrypt(row[0]) for row in db.execute("SELECT payload FROM listings ORDER BY rowid DESC")]

    def get(self, listing_id):
        with self.db() as db:
            row = db.execute("SELECT payload FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not row:
            raise KeyError("Draf tidak ditemui")
        return self.decrypt(row[0])

    def put(self, record, event="updated"):
        record["updated_at"] = now()
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO listings VALUES (?, ?)", (record["id"], self.encrypt(record)))
            self._audit(db, event, record["id"], {})

    def _audit(self, db, event, listing_id, detail):
        db.execute("INSERT INTO audit(created,event,listing_id,detail) VALUES (?,?,?,?)",
                   (now(), event, listing_id, self.encrypt(detail)))

    def audit(self, event, listing_id=None, detail=None):
        with self.db() as db:
            self._audit(db, event, listing_id, detail or {})

    def ingest(self, text, source, photo=None, photo_id=None, album_id=None, event_id=None):
        if photo is not None and len(photo) > MAX_PHOTO_BYTES:
            raise ValueError("Gambar melebihi had 10 MB.")
        # One transaction keeps replay checks and album accumulation crash safe.
        with self.db() as db:
            if event_id is not None and db.execute("SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone():
                return None, "replayed"
            records = [self.decrypt(r[0]) for r in db.execute("SELECT payload FROM listings")]
            record = next((r for r in records if album_id and r.get("album_id") == album_id), None)
            if record is None:
                exact = next((r for r in records if text.strip() and fingerprint(text) in r["text_hashes"]), None)
                exact_photo = next((r for r in records if photo_id and photo_id in r["photo_ids"]), None)
                match = exact or exact_photo
                # Keep new observations and their photos/source; never silently discard a new album.
                fields = extract(text)
                sig = property_signature(fields)
                candidates = [r["id"] for r in records if sig and property_signature(r["fields"]) == sig]
                if match and match["id"] not in candidates:
                    candidates.append(match["id"])
                record = {"id": uuid.uuid4().hex[:12], "created_at": now(), "fields": fields,
                          "originals": [], "sources": [], "photos": [], "photo_ids": [], "text_hashes": [],
                          "album_id": album_id, "reuse_confirmed": False,
                          "duplicate_candidates": candidates}
            else:
                # New content invalidates the prior permission confirmation.
                record["reuse_confirmed"] = False
            if text and text not in record["originals"]:
                record["originals"].append(text)
                record["text_hashes"].append(fingerprint(text))
                record["fields"] = extract("\n".join(record["originals"]))
            if source not in record["sources"]:
                record["sources"].append(source)
            if photo is not None and photo_id not in record["photo_ids"]:
                # Photos remain encrypted inside the encrypted record (base64 for JSON).
                import base64
                record["photos"].append({"data": base64.b64encode(photo).decode(),
                                         "sha256": hashlib.sha256(photo).hexdigest()})
                record["photo_ids"].append(photo_id)
            record["updated_at"] = now()
            db.execute("INSERT OR REPLACE INTO listings VALUES (?,?)", (record["id"], self.encrypt(record)))
            if event_id is not None:
                db.execute("INSERT INTO events VALUES (?)", (event_id,))
            self._audit(db, "listing_received", record["id"], {"duplicate_candidates": record["duplicate_candidates"]})
        return record, "received"
