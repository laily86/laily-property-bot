"""Conservative extraction. Unlabelled or ambiguous facts remain unknown."""
import hashlib
import re

from .sources import source_hashtags, source_needs_review

FIELDS = ("property_type", "location", "price", "bedrooms", "bathrooms", "floor_area",
          "tenure", "facilities", "agent_details", "availability")
LABELS = {
    "property_type": r"jenis(?: hartanah)?|property type|type",
    "location": r"lokasi|location|alamat|address",
    "price": r"harga|price|asking price",
    "bedrooms": r"bilik tidur|bedrooms?|rooms?",
    "bathrooms": r"bilik air|bathrooms?",
    "floor_area": r"keluasan(?: binaan)?|built[- ]?up|floor area",
    "tenure": r"pegangan|tenure",
    "facilities": r"kemudahan|facilities",
    "agent_details": r"ejen|agent(?: details)?|contact|hubungi",
    "availability": r"availability|ketersediaan|status ketersediaan",
}


def extract(text):
    result = {field: None for field in FIELDS}
    for field, labels in LABELS.items():
        matches = re.findall(rf"^(?:{labels})\s*[:=]\s*([^\n]+)$", text, re.I | re.M)
        values = list(dict.fromkeys(x.strip() for x in matches if x.strip()))
        if len(values) == 1:
            result[field] = values[0]
    # Never infer a rent period, currency, area unit or availability from context.
    result["availability_confirmed"] = False
    return result


def validate_edits(edits):
    if not isinstance(edits, dict) or not edits or set(edits) - set(FIELDS) - {"availability_confirmed"}:
        raise ValueError("Gunakan hanya medan yang disenaraikan dalam arahan Edit.")
    for k, v in edits.items():
        if k == "availability_confirmed":
            if type(v) is not bool:
                raise ValueError("availability_confirmed mesti true atau false.")
        elif v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 1500):
            raise ValueError("Nilai medan mesti teks 1–1500 aksara atau null.")
    return edits


def fingerprint(text):
    normalized = re.sub(r"\W+", " ", text.casefold()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def property_signature(fields):
    # Candidate only: matching attributes do not prove it is the same unit.
    keys = ("property_type", "location", "bedrooms", "bathrooms", "floor_area")
    if not all(fields.get(k) for k in keys):
        return None
    return fingerprint(" | ".join(fields[k] for k in keys))


def review_reasons(record):
    f = record["fields"]
    reasons = []
    for key in ("property_type", "location", "price", "bedrooms", "bathrooms", "floor_area", "tenure"):
        if not f.get(key):
            reasons.append(f"Belum diketahui: {key}")
    if not f.get("availability") or not f.get("availability_confirmed"):
        reasons.append("Ketersediaan perlu pengesahan manual.")
    # Prices must explicitly include RM, including an explicit period for rentals.
    price = f.get("price") or ""
    if price and not re.fullmatch(r"RM\s*\d[\d,]*(?:\.\d{1,2})?(?:\s*/\s*(?:bulan|month))?", price, re.I):
        reasons.append("Format harga perlu semakan (contoh RM 450,000 atau RM 1,500 / bulan).")
    if not record.get("reuse_confirmed"):
        reasons.append("Kebenaran penggunaan listing dan gambar belum disahkan.")
    if source_needs_review(record):
        reasons.append("Sumber channel tidak lengkap atau disembunyikan; hashtag perlu semakan manual.")
    if record.get("duplicate_candidates"):
        reasons.append("Kemungkinan hartanah pendua; semak rekod berkaitan.")
    return reasons


def generate(record, platform, contact_profile=None):
    if platform not in ("facebook", "mudah"):
        raise ValueError("Platform tidak sah")
    # Render a copy: original agent identity, REN and source records remain untouched.
    f = dict(record["fields"])
    if contact_profile is not None:
        f["agent_details"] = contact_profile.contact_text()
    title = " — ".join(x for x in (f.get("property_type"), f.get("location")) if x) or "Hartanah / Property"
    price = f.get("price") or "Belum diketahui / Unknown"
    bm_labels = {"property_type": "Jenis", "location": "Lokasi", "bedrooms": "Bilik tidur",
                 "bathrooms": "Bilik air", "floor_area": "Keluasan", "tenure": "Pegangan",
                 "facilities": "Kemudahan", "agent_details": "Maklumat ejen", "availability": "Ketersediaan (rujukan asal)"}
    en_labels = {"property_type": "Property type", "location": "Location", "bedrooms": "Bedrooms",
                 "bathrooms": "Bathrooms", "floor_area": "Floor area", "tenure": "Tenure",
                 "facilities": "Facilities", "agent_details": "Agent details", "availability": "Availability (original source)"}
    bm = [f"{label}: {f[k]}" for k, label in bm_labels.items() if f.get(k)]
    en = [f"{label}: {f[k]}" for k, label in en_labels.items() if f.get(k)]
    if platform == "facebook":
        bm = ["Maklumat hartanah untuk pertimbangan anda.", f"Harga: {price}", *bm]
        en = ["Property details for your consideration.", f"Price: {price}", *en]
    else:
        bm = ["BUTIRAN HARTANAH", *bm, f"Harga dinyatakan: {price}"]
        en = ["PROPERTY PARTICULARS", *en, f"Listed price: {price}"]
    if not f.get("availability_confirmed"):
        bm.append("Ketersediaan belum disahkan. Sila sahkan dengan pemilik atau ejen.")
        en.append("Availability is unconfirmed. Please confirm with the owner or agent.")
    hashtags = source_hashtags(record)
    if hashtags:
        bm.append(" ".join(hashtags))
        en.append(" ".join(hashtags))
    return {"platform": platform, "source_hashtags": hashtags, "title_bm": title, "title_en": title, "price": price,
            "description_bm": "\n".join(bm), "description_en": "\n".join(en),
            "review_reasons": review_reasons(record)}
