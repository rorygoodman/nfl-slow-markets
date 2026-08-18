from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamPrice:
    team_name: str
    selection_id: str
    decimal_odds: float


@dataclass(frozen=True)
class NFLGameOdds:
    """One NFL moneyline market: both teams' current decimal odds."""
    market_id: int
    event_id: str
    event_name: str          # e.g. "HOU Texans vs LV Raiders"
    kickoff_time: str        # ISO 8601 with UTC offset, from the item's startDate
    market_view_group_id: int
    teams: tuple[TeamPrice, TeamPrice]
