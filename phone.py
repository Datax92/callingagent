"""
Phone number helpers: validation/normalization for Pakistani mobile numbers,
and Urdu-script detection used to pick text direction/font in the UI.
"""
import re
from typing import Optional

URDU_RANGE_RE = re.compile(r"[\u0600-\u06FF]")

# Pakistani mobile: 03XXXXXXXXX (11 digits) -- the shape agents/dashboard
# users will actually type. Also accepts an already-international +92XXXXXXXXXX.
PK_LOCAL_RE = re.compile(r"^0(3\d{9})$")
E164_RE = re.compile(r"^\+\d{8,15}$")


def normalize_phone_number(raw: str) -> Optional[str]:
    """Best-effort normalize to E.164. Returns None if it doesn't look like a real number."""
    cleaned = re.sub(r"[\s\-()]", "", raw or "")
    if E164_RE.match(cleaned):
        return cleaned
    m = PK_LOCAL_RE.match(cleaned)
    if m:
        return "+92" + m.group(1)
    if cleaned.startswith("92") and len(cleaned) == 12 and cleaned.isdigit():
        return "+" + cleaned
    return None


def is_urdu(text: Optional[str]) -> bool:
    return bool(text and URDU_RANGE_RE.search(text))


def text_dir_attrs(text: Optional[str]) -> str:
    """HTML attribute string to make Urdu previews render RTL in the right font."""
    if is_urdu(text):
        return 'dir="rtl" lang="ur" class="urdu-text"'
    return 'dir="ltr"'
