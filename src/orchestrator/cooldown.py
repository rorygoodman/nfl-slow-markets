"""File-based cooldown tracking: has this (market, bookmaker) pair
already alerted recently? State lives in a small shared JSON file
rather than in the long-lived poll loop's memory, because cooldown
outcomes are only known AFTER a subprocess (orchestrator/pipeline.py)
finishes scraping and computing edges — the poll loop has no visibility
into that without this file. See the plan's Global Constraints for why
this doesn't conflict with the spec's "no cross-restart persistence"
non-goal."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_COOLDOWN = timedelta(minutes=30)


def default_cooldown_path() -> Path:
    return Path.home() / ".nfl-slow-markets" / "cooldown.json"


def load_cooldowns(path: Path) -> dict[str, str]:
    """Missing file, unreadable file, corrupt JSON, or JSON that isn't an
    object all fail open to an empty dict (never crash the pipeline)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_cooldowns(path: Path, cooldowns: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cooldowns, indent=2))


def _key(market_id: str, bookmaker: str) -> str:
    return f"{market_id}|{bookmaker}"


def is_in_cooldown(
    cooldowns: dict[str, str],
    market_id: str,
    bookmaker: str,
    now: datetime,
    window: timedelta = DEFAULT_COOLDOWN,
) -> bool:
    raw = cooldowns.get(_key(market_id, bookmaker))
    if raw is None:
        return False
    try:
        last_alerted = datetime.fromisoformat(raw)
    except ValueError:
        return False
    return now - last_alerted < window


def record_alert(cooldowns: dict[str, str], market_id: str, bookmaker: str, now: datetime) -> None:
    cooldowns[_key(market_id, bookmaker)] = now.isoformat()
