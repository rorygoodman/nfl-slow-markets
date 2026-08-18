from __future__ import annotations

from matching.matcher import match_game, parse_polymarket_teams, team_price_for
from matching.models import BookmakerGame, BookmakerTeamPrice

COMMANDERS_LIONS_PADDYPOWER = BookmakerGame(
    bookmaker="Paddy Power",
    event_name="Washington Commanders @ Detroit Lions",
    kickoff_time="2026-08-22T16:00:00.000Z",
    teams=(
        BookmakerTeamPrice(team_name="Washington Commanders", decimal_odds=2.6),
        BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.444444444444444),
    ),
)
COMMANDERS_LIONS_NOVIBET = BookmakerGame(
    bookmaker="Novibet",
    event_name="DET Lions vs WAS Commanders",
    kickoff_time="2026-08-22T16:00:00+00:00",
    teams=(
        BookmakerTeamPrice(team_name="DET Lions", decimal_odds=1.42),
        BookmakerTeamPrice(team_name="WAS Commanders", decimal_odds=2.8),
    ),
)
OTHER_GAME = BookmakerGame(
    bookmaker="Paddy Power",
    event_name="Chicago Bears @ Detroit Lions",
    kickoff_time="2026-11-26T18:00:00.000Z",
    teams=(
        BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=2.1),
        BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.727272727272727),
    ),
)


def test_parses_a_polymarket_question_with_period():
    assert parse_polymarket_teams("Commanders vs. Lions") == ("commanders", "lions")


def test_parses_a_polymarket_question_without_period():
    assert parse_polymarket_teams("Lions vs Colts") == ("lions", "colts")


def test_parse_returns_none_for_unrecognized_shape():
    assert parse_polymarket_teams("Will the Lions make the playoffs?") is None


def test_parse_returns_none_for_unrecognized_team_name():
    assert parse_polymarket_teams("Sharks vs. Lions") is None


def test_matches_the_correct_game_by_team_pair_and_kickoff():
    matched = match_game(
        "Commanders vs. Lions", "2026-08-22 16:00:00+00",
        [OTHER_GAME, COMMANDERS_LIONS_PADDYPOWER],
    )
    assert matched == COMMANDERS_LIONS_PADDYPOWER


def test_does_not_match_on_team_pair_alone_when_kickoff_differs():
    other_time_same_teams = BookmakerGame(
        bookmaker="Paddy Power", event_name="Washington Commanders @ Detroit Lions",
        kickoff_time="2026-12-25T18:00:00.000Z",
        teams=COMMANDERS_LIONS_PADDYPOWER.teams,
    )
    matched = match_game("Commanders vs. Lions", "2026-08-22 16:00:00+00", [other_time_same_teams])
    assert matched is None


def test_returns_none_when_no_candidate_matches():
    matched = match_game("Commanders vs. Lions", "2026-08-22 16:00:00+00", [OTHER_GAME])
    assert matched is None


def test_returns_none_for_unparseable_polymarket_question():
    matched = match_game("not a question", "2026-08-22 16:00:00+00", [COMMANDERS_LIONS_PADDYPOWER])
    assert matched is None


def test_team_price_for_finds_the_right_team():
    price = team_price_for(COMMANDERS_LIONS_PADDYPOWER, "Commanders")
    assert price == BookmakerTeamPrice(team_name="Washington Commanders", decimal_odds=2.6)


def test_team_price_for_returns_none_when_team_not_in_game():
    assert team_price_for(COMMANDERS_LIONS_PADDYPOWER, "Raiders") is None


def test_full_three_way_real_match():
    """The flagship end-to-end proof: real Polymarket + real Paddy Power +
    real Novibet data for the same real game, matched and priced
    correctly against both bookmakers independently."""
    polymarket_question = "Commanders vs. Lions"
    polymarket_kickoff = "2026-08-22 16:00:00+00"
    polymarket_tracked_outcome = "Commanders"  # outcomes[0], per polymarket_monitor's convention

    pp_match = match_game(polymarket_question, polymarket_kickoff, [COMMANDERS_LIONS_PADDYPOWER])
    novibet_match = match_game(polymarket_question, polymarket_kickoff, [COMMANDERS_LIONS_NOVIBET])

    assert pp_match is not None
    assert novibet_match is not None

    pp_price = team_price_for(pp_match, polymarket_tracked_outcome)
    novibet_price = team_price_for(novibet_match, polymarket_tracked_outcome)

    assert pp_price.decimal_odds == 2.6
    assert novibet_price.decimal_odds == 2.8
