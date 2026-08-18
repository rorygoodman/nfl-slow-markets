from __future__ import annotations

from novibet_scraper.models import NFLGameOdds as NovibetGameOdds
from novibet_scraper.models import TeamPrice as NovibetTeamPrice
from paddypower_scraper.models import NFLGameOdds as PaddyPowerGameOdds
from paddypower_scraper.models import TeamPrice as PaddyPowerTeamPrice

from matching.adapters import from_novibet, from_paddypower
from matching.models import BookmakerGame, BookmakerTeamPrice


def test_from_paddypower_adapts_a_real_captured_game():
    game = PaddyPowerGameOdds(
        market_id="927.397323416",
        event_id="35950165",
        event_name="Washington Commanders @ Detroit Lions",
        kickoff_time="2026-08-22T16:00:00.000Z",
        competition_id=11432305,
        teams=(
            PaddyPowerTeamPrice(team_name="Washington Commanders", selection_id=42568622,
                                 decimal_odds=2.6, home_or_away="AWAY"),
            PaddyPowerTeamPrice(team_name="Detroit Lions", selection_id=50193,
                                 decimal_odds=1.444444444444444, home_or_away="HOME"),
        ),
    )

    adapted = from_paddypower(game)

    assert adapted == BookmakerGame(
        bookmaker="Paddy Power",
        event_name="Washington Commanders @ Detroit Lions",
        kickoff_time="2026-08-22T16:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Washington Commanders", decimal_odds=2.6),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.444444444444444),
        ),
    )


def test_from_novibet_adapts_a_real_captured_game():
    game = NovibetGameOdds(
        market_id=1709836920,
        event_id="47678020",
        event_name="DET Lions vs WAS Commanders",
        kickoff_time="2026-08-22T16:00:00+00:00",
        market_view_group_id=5813718,
        teams=(
            NovibetTeamPrice(team_name="DET Lions", selection_id="7127413140", decimal_odds=1.42),
            NovibetTeamPrice(team_name="WAS Commanders", selection_id="7127413141", decimal_odds=2.8),
        ),
    )

    adapted = from_novibet(game)

    assert adapted == BookmakerGame(
        bookmaker="Novibet",
        event_name="DET Lions vs WAS Commanders",
        kickoff_time="2026-08-22T16:00:00+00:00",
        teams=(
            BookmakerTeamPrice(team_name="DET Lions", decimal_odds=1.42),
            BookmakerTeamPrice(team_name="WAS Commanders", decimal_odds=2.8),
        ),
    )
