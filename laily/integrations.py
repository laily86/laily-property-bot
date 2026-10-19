"""No platform account access, browser automation, or publishing paths exist."""
from enum import StrEnum


class Status(StrEnum):
    LOCAL_DRAFT = "LOCAL_DRAFT"
    PLATFORM_DRAFT_SAVED = "PLATFORM_DRAFT_SAVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INTEGRATION_UNAVAILABLE = "INTEGRATION_UNAVAILABLE"
    ERROR = "ERROR"


def platform_status(platform):
    if platform not in ("facebook", "mudah"):
        raise ValueError("Platform tidak sah")
    return {"status": Status.INTEGRATION_UNAVAILABLE,
            "reason": "Kaedah rasmi untuk menyimpan draf akaun belum disahkan. Gunakan pakej manual.",
            "verified_draft_url": None}
