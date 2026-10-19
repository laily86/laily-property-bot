"""Offline example, no Telegram or platform credentials required."""
import argparse
from pathlib import Path
from cryptography.fernet import Fernet
from .storage import Store
from .listings import generate

SAMPLE = """Jenis: Kondominium
Lokasi: Kajang
Harga: RM 450,000
Bilik tidur: 3
Bilik air: 2
Keluasan: 1,000 sqft
Pegangan: Leasehold
Kemudahan: Kolam renang
Ejen: Ejen Contoh (data rekaan untuk ujian sahaja)"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    # Deliberately ephemeral: demo fixtures cannot be mistaken for real listings.
    with __import__('tempfile').TemporaryDirectory(dir=args.data_dir.parent) as directory:
        store = Store(Path(directory), Fernet.generate_key())
        record, _ = store.ingest(SAMPLE, {"kind": "SAMPLE_ONLY"})
        for platform in ("facebook", "mudah"):
            draft = generate(record, platform)
            print(platform.upper(), "LOCAL_DRAFT / NEEDS_REVIEW / INTEGRATION_UNAVAILABLE")
            print(draft["description_bm"])
            print(draft["description_en"])


if __name__ == "__main__":
    main()
