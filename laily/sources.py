"""Source tags derived only from Telegram forward metadata, never listing text."""
import re
from urllib.parse import urlsplit

CHANNEL_TAGS = {
    "umairpropertylisting": "#xum",
    "ejenhartanah_sufi": "#xsfi",
    "brotherkhaiproperty": "#xkhi",
    "asrizadbakrilisting": "#xas",
    "blacky_listing_property": "#nrhfdz",
}


def source_username(source):
    username = source.get("channel_username")
    if isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", username.lstrip("@")):
        return username.lstrip("@").lower()
    # Backward compatibility: older records saved public source URLs, not usernames.
    url = source.get("source_url")
    if isinstance(url, str):
        try:
            parsed = urlsplit(url)
            if parsed.scheme == "https" and parsed.netloc.lower() == "t.me":
                match = re.fullmatch(r"/([A-Za-z0-9_]{1,64})/[0-9]+/?", parsed.path)
                if match and match[1].lower() not in {"c", "s"}:
                    return match[1].lower()
        except ValueError:
            pass
    return None


def source_tag(source):
    username = source_username(source)
    if username in CHANNEL_TAGS:
        return CHANNEL_TAGS[username]
    # A readable channel title is the default for channels without a custom code.
    title = source.get("chat_title")
    name = title if isinstance(title, str) and title.strip() else username
    if not name:
        return None
    tag = "".join(c for c in re.sub(r"\s+", "_", name.strip()) if c.isalnum() or c == "_")
    tag = re.sub(r"_+", "_", tag).strip("_")[:100]
    return "#" + tag if tag else None


def source_hashtags(record):
    return list(dict.fromkeys(tag for source in record.get("sources", []) if (tag := source_tag(source))))


def source_needs_review(record):
    sources = record.get("sources", [])
    return not sources or any(source_tag(source) is None for source in sources)


def remove_listing_hashtags(text):
    """Remove promotional tags while preserving URLs and numbered property units."""
    pattern = re.compile(r"https?://[^\s]+|(?<![\w/])#[\w]+", re.UNICODE)

    def replace(match):
        token = match.group()
        if token.startswith(('http://', 'https://')):
            return token
        before, after = text[:match.start()], text[match.end():]
        # #12, #12-03 and Unit #A12 can be factual unit numbers, not hashtags.
        if token[1:].isdigit() or re.match(r"[-/]\d", after) or re.search(r"\b(?:unit|lot|no\.?)\s*$", before, re.I):
            return token
        return ''

    cleaned = pattern.sub(replace, text)
    return '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in cleaned.splitlines()).strip()
