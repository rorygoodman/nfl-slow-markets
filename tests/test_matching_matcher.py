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


def test_match_game_is_independent_of_team_order_within_the_bookmaker_game():
    """The unordered team-pair matching property (frozenset comparison,
    not positional) is the most important correctness property in this
    module. This test demonstrates it synthetically, independent of any
    fixture's incidental team ordering: two BookmakerGames for the same
    team pair and kickoff, one with teams=(A, B) and one with teams=(B, A),
    both matched successfully by the same Polymarket question."""
    forward_order = BookmakerGame(
        bookmaker="Paddy Power",
        event_name="Chicago Bears @ Carolina Panthers",
        kickoff_time="2026-09-13T17:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=2.2),
            BookmakerTeamPrice(team_name="Carolina Panthers", decimal_odds=1.7),
        ),
    )
    reversed_order = BookmakerGame(
        bookmaker="Paddy Power",
        event_name="Carolina Panthers @ Chicago Bears",
        kickoff_time="2026-09-13T17:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Carolina Panthers", decimal_odds=1.7),
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=2.2),
        ),
    )

    matched_forward = match_game(
        "Bears vs. Panthers", "2026-09-13 17:00:00+00", [forward_order],
    )
    matched_reversed = match_game(
        "Bears vs. Panthers", "2026-09-13 17:00:00+00", [reversed_order],
    )

    assert matched_forward == forward_order
    assert matched_reversed == reversed_order


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
