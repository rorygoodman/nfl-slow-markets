"""Parse kickoff-time strings from any of this project's three data
sources into a single UTC instant, for cross-source comparison."""

from __future__ import annotations

from datetime import datetime, timezone


def to_instant(value) -> "datetime | None":
    """Accepts Polymarket's "2026-08-22 16:00:00+00" (space separator,
    bare 2-digit UTC offset), Paddy Power's "2026-08-22T16:00:00.000Z",
    or Novibet's "2026-08-22T16:00:00+00:00". Returns a UTC datetime, or
    None if `value` isn't a non-empty string or isn't parseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
