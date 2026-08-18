from __future__ import annotations

from novibet_scraper.models import NFLGameOdds as NovibetGameOdds
from paddypower_scraper.models import NFLGameOdds as PaddyPowerGameOdds

from .models import BookmakerGame, BookmakerTeamPrice


def from_paddypower(game: PaddyPowerGameOdds) -> BookmakerGame:
    t1, t2 = game.teams
    return BookmakerGame(
        bookmaker="Paddy Power",
        event_name=game.event_name,
        kickoff_time=game.kickoff_time,
        teams=(
            BookmakerTeamPrice(team_name=t1.team_name, decimal_odds=t1.decimal_odds),
            BookmakerTeamPrice(team_name=t2.team_name, decimal_odds=t2.decimal_odds),
        ),
    )


def from_novibet(game: NovibetGameOdds) -> BookmakerGame:
    t1, t2 = game.teams
    return BookmakerGame(
        bookmaker="Novibet",
        event_name=game.event_name,
        kickoff_time=game.kickoff_time,
        teams=(
            BookmakerTeamPrice(team_name=t1.team_name, decimal_odds=t1.decimal_odds),
            BookmakerTeamPrice(team_name=t2.team_name, decimal_odds=t2.decimal_odds),
        ),
    )
