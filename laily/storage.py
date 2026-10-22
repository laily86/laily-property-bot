import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from .listings import effective_fields, extract, fingerprint, property_signature

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
                CREATE TABLE IF NOT EXISTS preferences (name TEXT PRIMARY KEY, payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY);
            ''')
            # Fail closed before any new writes if the supplied key cannot open existing data.
            sample = db.execute("SELECT payload FROM listings LIMIT 1").fetchone()
            if sample is None:
                sample = db.execute("SELECT detail FROM audit LIMIT 1").fetchone()
            if sample is None:
                sample = db.execute("SELECT payload FROM preferences LIMIT 1").fetchone()
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

    def all(self, include_merged=False):
        with self.db() as db:
            records = [self.decrypt(row[0]) for row in db.execute("SELECT payload FROM listings ORDER BY rowid DESC")]
        return records if include_merged else [r for r in records if not r.get("merged_into")]

    def get(self, listing_id):
        with self.db() as db:
            row = db.execute("SELECT payload FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not row:
            raise KeyError("Draf tidak ditemui")
        record = self.decrypt(row[0])
        if record.get("merged_into"):
            return self.get(record["merged_into"])
        return record

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
            if record and record.get("merged_into"):
                while record.get("merged_into"):
                    record = next(r for r in records if r["id"] == record["merged_into"])
            if record is None:
                records = [r for r in records if not r.get("merged_into")]
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

    def contact_profile(self):
        from .profile import ContactProfile
        with self.db() as db:
            row = db.execute("SELECT payload FROM preferences WHERE name='contact_profile'").fetchone()
        return ContactProfile(**self.decrypt(row[0])) if row else None

    def set_contact_profile(self, profile):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES ('contact_profile', ?)",
                       (self.encrypt(profile.to_dict()),))
            self._audit(db, "contact_profile_updated", None, profile.to_dict())

    def preview_ids(self, listing_id, platform, chat_id):
        name = f"preview:{chat_id}:{platform}:{listing_id}"
        with self.db() as db:
            row = db.execute("SELECT payload FROM preferences WHERE name=?", (name,)).fetchone()
        return self.decrypt(row[0]) if row else []

    def save_preview_ids(self, listing_id, platform, chat_id, ids):
        name = f"preview:{chat_id}:{platform}:{listing_id}"
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES (?,?)", (name, self.encrypt(ids)))

    def merge_photos(self, target_id, source_id):
        """Explicit user-selected merge. Preserve both original records atomically."""
        if target_id == source_id:
            raise ValueError("Pilih dua draf berbeza.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = {r[0]: self.decrypt(r[1]) for r in db.execute(
                "SELECT id,payload FROM listings WHERE id IN (?,?)", (target_id, source_id))}
            if len(rows) != 2:
                raise KeyError("Draf tidak ditemui.")
            target, source = rows[target_id], rows[source_id]
            if source.get("merged_into") == target_id:
                return target
            if target.get("merged_into") or source.get("merged_into"):
                raise ValueError("Draf telah digabung. Buka semula /drafts.")
            if not source["photos"] or not target["originals"]:
                raise ValueError("Pilih draf gambar sebagai sumber dan draf teks sebagai sasaran.")
            fields = effective_fields(target)
            incoming = effective_fields(source)
            for key, value in incoming.items():
                if key in ("availability_confirmed", "agent_details"):
                    continue
                if value and fields.get(key) and value != fields[key]:
                    raise ValueError("Fakta kedua-dua draf bercanggah. Semak dan Edit dahulu: " + key)
                if value and not fields.get(key):
                    fields[key] = value
            target["fields"] = fields
            target["fields"]["availability_confirmed"] = False
            for key in ("originals", "sources", "text_hashes", "photo_ids"):
                for value in source[key]:
                    if value not in target[key]:
                        target[key].append(value)
            hashes = {photo["sha256"] for photo in target["photos"]}
            for photo in source["photos"]:
                if photo["sha256"] not in hashes:
                    target["photos"].append(photo)
                    hashes.add(photo["sha256"])
            target["duplicate_candidates"] = list(dict.fromkeys(
                x for x in target["duplicate_candidates"] + source["duplicate_candidates"]
                if x not in (source_id, target_id)))
            target["reuse_confirmed"] = False
            target["updated_at"] = now()
            source["merged_into"] = target_id
            source["reuse_confirmed"] = False
            for record in (target, source):
                db.execute("UPDATE listings SET payload=? WHERE id=?", (self.encrypt(record), record["id"]))
            self._audit(db, "photos_merged_by_user", target_id, {"source_id": source_id})
        return target
