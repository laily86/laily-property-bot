"""Contact information explicitly supplied by the authorized user."""
import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ContactProfile:
    name: str
    whatsapp: str
    ren: str = ""
    agency: str = ""

    @classmethod
    def parse(cls, text):
        parts = [part.strip() for part in text.split("|")]
        if not 2 <= len(parts) <= 4:
            raise ValueError("Format: /profile Nama | WhatsApp | REN (pilihan) | Agensi (pilihan)")
        parts += [""] * (4 - len(parts))
        name, phone, ren, agency = parts
        if not name or len(name) > 100 or any("\n" in value or "\r" in value for value in parts):
            raise ValueError("Nama mesti 1–100 aksara; profil mesti dalam satu baris.")
        phone = re.sub(r"[\s()+-]", "", phone)
        if not re.fullmatch(r"[1-9][0-9]{7,14}", phone):
            raise ValueError("Gunakan nombor WhatsApp dengan kod negara, contohnya 60123456789 (bukan 012…).")
        if ren and not re.fullmatch(r"REN\s*[0-9]{3,8}", ren, re.I):
            raise ValueError("REN pilihan mesti nombor REN anda sendiri, contohnya REN 12345; atau kosongkan.")
        if len(agency) > 150:
            raise ValueError("Nama agensi maksimum 150 aksara.")
        return cls(name, phone, ren.upper(), agency)

    def to_dict(self):
        return asdict(self)

    def contact_text(self):
        return "\n".join(value for value in (
            self.name, f"WhatsApp: https://wa.me/{self.whatsapp}", self.ren, self.agency) if value)
