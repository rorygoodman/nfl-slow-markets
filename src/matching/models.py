from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookmakerTeamPrice:
    team_name: str
    decimal_odds: float


@dataclass(frozen=True)
class BookmakerGame:
    """Bookmaker-agnostic view of one NFL moneyline market. Whichever
    scraper it came from, it's adapted into this common shape before
    matching logic ever sees it."""
    bookmaker: str          # "Paddy Power" | "Novibet"
    event_name: str
    kickoff_time: str
    teams: tuple[BookmakerTeamPrice, BookmakerTeamPrice]
