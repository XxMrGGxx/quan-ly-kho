from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


# =========================
# Parsing / Formatting rules
# =========================
# DB rule (for nghiệp vụ): store *_date as YYYY-MM-DD
# UI/Excel rule: display dd/mm/yyyy


def _ensure_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def parse_to_date(value: Any) -> Optional[date]:
    """
    Parse various inputs into datetime.date.
    Accepts:
    - None / "" => None
    - datetime/date => date
    - 'YYYY-MM-DD' => date
    - 'YYYY-MM-DDTHH:MM:SS...' => date part
    - ISO with 'Z' suffix
    - 'dd/mm/yyyy' or 'dd-mm-yyyy'
    - unix timestamp (seconds/millis) if number-like
    """
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    s = _ensure_str(value).strip()
    if not s:
        return None

    # unix timestamp (seconds or millis)
    if s.isdigit():
        try:
            n = int(s)
            # heuristic: millis if too large
            if n > 10_000_000_000:
                n = n // 1000
            return datetime.fromtimestamp(n).date()
        except Exception:
            pass

    # Normalize ISO Z
    if isinstance(s, str) and s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s

    # Try ISO first (covers YYYY-MM-DD and full datetime)
    try:
        dt = datetime.fromisoformat(s2)
        return dt.date()
    except Exception:
        pass

    # Try common day/month formats
    # dd/mm/yyyy or dd-mm-yyyy
    for sep in ("/", "-"):
        parts = s.split(sep)
        if len(parts) == 3:
            a, b, c_ = parts
            # If first part is 4 digits => maybe YYYY-MM-DD but isoformat would have caught; still safe
            if len(a) == 4 and a.isdigit():
                # YYYY-MM-DD
                try:
                    return datetime(int(a), int(b), int(c_)).date()
                except Exception:
                    continue

            # assume dd/mm/yyyy
            try:
                dd = int(a)
                mm = int(b)
                yyyy = int(c_)
                return date(yyyy, mm, dd)
            except Exception:
                continue

    return None


def normalize_date_yyyy_mm_dd(value: Any) -> Optional[str]:
    """Return YYYY-MM-DD or None."""
    d = parse_to_date(value)
    if not d:
        return None
    return d.strftime("%Y-%m-%d")


def format_date_dd_mm_yyyy(value: Any) -> str:
    """Format value into dd/mm/yyyy for UI/Excel. If cannot parse => return original string."""
    if value is None:
        return ""
    d = parse_to_date(value)
    if not d:
        # fallback: preserve old behavior "as string"
        return _ensure_str(value)
    return d.strftime("%d/%m/%Y")


def normalize_date_range(start_date: Any, end_date: Any) -> tuple[Optional[str], Optional[str]]:
    """
    Normalize start/end to YYYY-MM-DD and ensure start <= end (if both exist).
    """
    sd = parse_to_date(start_date)
    ed = parse_to_date(end_date)

    if sd and ed and sd > ed:
        sd, ed = ed, sd

    return (
        sd.strftime("%Y-%m-%d") if sd else None,
        ed.strftime("%Y-%m-%d") if ed else None,
    )
