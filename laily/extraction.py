"""Conservative headline extraction; never infer geography from photographs."""
import re

# Specific building types precede broader ones so one headline gives one type.
TYPE_PATTERNS = [
    (r"(?:double|2|two)[ -]*(?:storey|story|tingkat)\s+(?:terrace(?:d)?(?: house)?|teres)", "2 Storey Terrace"),
    (r"(?:single|1|one)[ -]*(?:storey|story|tingkat)\s+(?:terrace(?:d)?(?: house)?|teres)", "Single Storey Terrace"),
    (r"rumah teres\s*2\s*tingkat", "Rumah Teres 2 Tingkat"),
    (r"rumah teres\s*(?:1|satu)\s*tingkat", "Rumah Teres 1 Tingkat"),
    (r"(?:tanah\s+(?:pertanian|komersial|kediaman|lot)|(?:agricultural|commercial|residential)\s+land)", None),
    (r"(?:apartment|apartmen|pangsapuri)", "Apartment"),
    (r"(?:condominium|kondominium|condo)", "Condominium"),
    (r"(?:serviced?\s+(?:apartment|residence)|residensi servis)", "Serviced Apartment"),
    (r"(?:semi[- ]?d(?:etached)?(?: house)?|rumah berkembar)", "Semi-D"),
    (r"(?:bungalow|banglo)", "Bungalow"),
    (r"(?:terrace(?:d)? house|rumah teres|teres)", "Terrace House"),
    (r"(?:shop\s*lot|shop\s*house|kedai)", "Shoplot"),
    (r"(?:flat|studio|townhouse)", None),
    (r"(?:tanah|land)(?!\s*(?:area|size|title|tenure))", None),
]
PREFIX = re.compile(r"^(?:(?:untuk\s+)?(?:di\s*)?(?:jual|sewa)|for\s+(?:sale|rent)|wts|wtl|wtr|selling|rental)\b\s*[:|!—–-]*\s*", re.I)
STOP = re.compile(r"\b(?:near(?:by)?|berdekatan|amenities|facilities|kemudahan|access|akses|agent|ejen|contact|hubungi)\b", re.I)


def headline_facts(text):
    candidates = []
    for raw in text.splitlines()[:12]:
        line = raw.strip().strip('•*✅📍🏠🏡 ').strip()
        if not line or line.startswith(('http', '#')) or STOP.search(line):
            continue
        line = PREFIX.sub('', line).strip()
        # Facts/advertising sections are not property headlines. Address handled by labels.
        if re.match(r"(?:land area|keluasan tanah|built.up|floor area|price|harga|deposit)\b", line, re.I):
            continue
        for pattern, canonical in TYPE_PATTERNS:
            match = re.match(rf"(?:{pattern})\b", line, re.I)
            if not match:
                continue
            kind = canonical or match.group().strip()
            tail = line[match.end():].strip()
            # 'Apartment / Condo' is ambiguous, not an address.
            if any(re.match(rf"^[ /&,-]*(?:{other})\b", tail, re.I) for other, _ in TYPE_PATTERNS):
                candidates.append((kind, None))
                candidates.append(('AMBIGUOUS', None))
                break
            tail = PREFIX.sub('', tail).strip()
            tail = re.sub(r"^(?:di|at|in)\b\s*|^[@:|—–-]+\s*", '', tail, flags=re.I).strip()
            tail = re.split(r"\s+(?:[-|—–]|RM\s*\d)|\s+(?:for sale|for rent|untuk dijual|untuk disewa)\b", tail, maxsplit=1, flags=re.I)[0].strip()
            location = tail if (tail and len(tail) <= 180 and re.search(r"[^\W\d_]", tail) and
                                not re.search(r"\b(?:bedrooms?|bathrooms?|sqft|freehold|leasehold|tingkat|storey|available|fully|furnished|with|ready|wanted|is|are)\b|[:=]", tail, re.I)) else None
            candidates.append((kind, location))
            break
    kinds = list(dict.fromkeys(kind.casefold() for kind, _ in candidates))
    locations = list(dict.fromkeys(loc for _, loc in candidates if loc))
    return {"property_type": candidates[0][0] if len(kinds) == 1 else None,
            "location": locations[0] if len(kinds) == 1 and len(locations) == 1 else None}


def unlabelled_room_count(text, field):
    suffix = r"(?:bedrooms?|bilik tidur)" if field == 'bedrooms' else r"(?:bathrooms?|bilik air)"
    values = list(dict.fromkeys(re.findall(rf"(?<![\w.+])([0-9]{{1,2}})\s+{suffix}\b", text, re.I)))
    return values[0] if len(values) == 1 else None


def is_land(property_type):
    return bool(property_type and re.fullmatch(
        r"(?:tanah(?:\s+(?:lot|pertanian|komersial|kediaman))?|(?:(?:agricultural|commercial|residential)\s+)?land)",
        property_type.strip(), re.I))
