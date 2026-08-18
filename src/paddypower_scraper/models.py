from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamPrice:
    team_name: str
    selection_id: int
    decimal_odds: float
    home_or_away: str  # "HOME" | "AWAY"


@dataclass(frozen=True)
class NFLGameOdds:
    """One NFL moneyline market: both teams' current decimal odds."""
    market_id: str
    event_id: str
    event_name: str          # e.g. "Chicago Bears @ Detroit Lions" ("Away @ Home")
    kickoff_time: str        # ISO 8601 UTC, from the event's openDate
    competition_id: int
    teams: tuple[TeamPrice, TeamPrice]
