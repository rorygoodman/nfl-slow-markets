"""Canonical NFL team nickname registry and lookup.

Every team's nickname is a single token, and every data source this
project scrapes always places the nickname last ("Raiders",
"Las Vegas Raiders", "LV Raiders" all end in "Raiders") — verified
against real captured output from Polymarket, Paddy Power, and Novibet.
"""

from __future__ import annotations

import re

CANONICAL_NICKNAMES = frozenset({
    "cardinals", "falcons", "ravens", "bills", "panthers", "bears",
    "bengals", "browns", "cowboys", "broncos", "lions", "packers",
    "texans", "colts", "jaguars", "chiefs", "raiders", "chargers",
    "rams", "dolphins", "vikings", "patriots", "saints", "giants",
    "jets", "eagles", "steelers", "49ers", "seahawks", "buccaneers",
    "titans", "commanders",
})


def _fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def normalize_team_nickname(name) -> "str | None":
    """Extract the last whitespace-separated token from `name` and
    validate it against the canonical NFL nickname registry. Returns the
    canonical lowercase nickname, or None if `name` isn't a non-empty
    string or its last token isn't a recognized nickname — fails safe
    rather than guessing."""
    if not isinstance(name, str) or not name.strip():
        return None
    last_token = name.strip().split()[-1]
    folded = _fold(last_token)
    return folded if folded in CANONICAL_NICKNAMES else None
