import base64
import io
import json
import zipfile

from .integrations import platform_status
from .listings import generate


def manual_package(record, platform):
    if not record.get("reuse_confirmed"):
        raise PermissionError("Sahkan kebenaran menggunakan listing dan SEMUA gambar terlebih dahulu.")
    draft = generate(record, platform)
    draft["integration"] = platform_status(platform)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("draft.json", json.dumps(draft, ensure_ascii=False, indent=2))
        archive.writestr("original-and-source.json", json.dumps(
            {"originals": record["originals"], "sources": record["sources"]}, ensure_ascii=False, indent=2))
        archive.writestr("BACA-DAHULU.txt", "DRAF MANUAL SAHAJA. Tiada draf disimpan dalam akaun platform.\n"
                          "Semak semua fakta, harga, kebenaran dan ketersediaan. Jangan terbitkan melalui aplikasi ini.\n"
                          "Pakej ini tidak disulitkan supaya boleh dibaca. Simpan di lokasi selamat dan padam selepas digunakan.\n")
        for i, photo in enumerate(record["photos"], 1):
            archive.writestr(f"photos/{i:02d}.jpg", base64.b64decode(photo["data"]))
    buffer.seek(0)
    return buffer
