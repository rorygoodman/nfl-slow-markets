from __future__ import annotations

from datetime import datetime, timezone

from matching.models import BookmakerGame, BookmakerTeamPrice
from notifier.models import ValueBetAlert
from polymarket_monitor.models import MoveEvent

from arb_finder.finder import find_value_bets

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

# Real captured data: Polymarket's Commanders price moved 0.30 -> 0.36
# (a genuine >=5% relative move), matched against the real Paddy Power and
# Novibet games for this exact game (see matching's own test suite).
REAL_MOVE = MoveEvent(
    market_id="m1", question="Commanders vs. Lions", tracked_outcome="Commanders",
    old_price=0.30, new_price=0.36, relative_move=0.20,
    old_at=NOW, new_at=NOW, game_start_time="2026-08-22 16:00:00+00",
)
REAL_PADDYPOWER_GAME = BookmakerGame(
    bookmaker="Paddy Power", event_name="Washington Commanders @ Detroit Lions",
    kickoff_time="2026-08-22T16:00:00.000Z",
    teams=(
        BookmakerTeamPrice(team_name="Washington Commanders", decimal_odds=2.6),
        BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.444444444444444),
    ),
)
REAL_NOVIBET_GAME = BookmakerGame(
    bookmaker="Novibet", event_name="DET Lions vs WAS Commanders",
    kickoff_time="2026-08-22T16:00:00+00:00",
    teams=(
        BookmakerTeamPrice(team_name="DET Lions", decimal_odds=1.42),
        BookmakerTeamPrice(team_name="WAS Commanders", decimal_odds=2.8),
    ),
)

# Synthetic: a game where the bookmaker price genuinely hasn't caught up
# to Polymarket's new fair price — a real positive-edge opportunity.
STALE_MOVE = MoveEvent(
    market_id="m2", question="Bears vs. Lions", tracked_outcome="Bears",
    old_price=0.40, new_price=0.60, relative_move=0.50,
    old_at=NOW, new_at=NOW, game_start_time="2026-11-26 18:00:00+00",
)
STALE_PADDYPOWER_GAME = BookmakerGame(
    bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
    kickoff_time="2026-11-26T18:00:00.000Z",
    teams=(
        # true_prob=0.60; decimal_odds=2.00 -> edge = 2.00*0.60-1 = +0.20
        BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=2.00),
        BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.80),
    ),
)
STALE_NOVIBET_GAME = BookmakerGame(
    bookmaker="Novibet", event_name="DET Lions vs CHI Bears",
    kickoff_time="2026-11-26T18:00:00+00:00",
    teams=(
        BookmakerTeamPrice(team_name="DET Lions", decimal_odds=1.75),
        # true_prob=0.60; decimal_odds=1.90 -> edge = 1.90*0.60-1 = +0.14
        BookmakerTeamPrice(team_name="CHI Bears", decimal_odds=1.90),
    ),
)


def test_real_data_both_legs_below_threshold_returns_empty():
    """Sanity check against genuinely real market data: a healthy,
    roughly-efficient market should NOT produce a value bet here — both
    real bookmaker prices imply a lower Commanders probability than
    Polymarket's, i.e. negative edge, correctly filtered out."""
    alerts = find_value_bets(REAL_MOVE, [REAL_PADDYPOWER_GAME], [REAL_NOVIBET_GAME])
    assert alerts == []


def test_finds_and_ranks_both_legs_when_both_clear_the_threshold():
    alerts = find_value_bets(STALE_MOVE, [STALE_PADDYPOWER_GAME], [STALE_NOVIBET_GAME])

    assert len(alerts) == 2
    assert alerts[0].bookmaker == "Paddy Power"  # +20% edge, ranked first
    assert alerts[1].bookmaker == "Novibet"      # +14% edge, ranked second
    assert round(alerts[0].edge, 6) == 0.20
    assert round(alerts[1].edge, 6) == 0.14


def test_alert_fields_are_populated_correctly():
    alerts = find_value_bets(STALE_MOVE, [STALE_PADDYPOWER_GAME], [])

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert == ValueBetAlert(
        game_name="Bears vs. Lions",
        team_name="Chicago Bears",
        bookmaker="Paddy Power",
        decimal_odds=2.00,
        polymarket_old_price=0.40,
        polymarket_new_price=0.60,
        polymarket_relative_move=0.5,   # SIGNED: (0.60-0.40)/0.40 = +0.5
        edge=0.20,
    )


def test_relative_move_is_negative_when_price_falls():
    falling_move = MoveEvent(
        market_id="m3", question="Bears vs. Lions", tracked_outcome="Bears",
        old_price=0.60, new_price=0.40, relative_move=0.333333333333333,
        old_at=NOW, new_at=NOW, game_start_time="2026-11-26 18:00:00+00",
    )
    # decimal_odds=2.00, true_prob=0.40 -> edge = 2.00*0.40-1 = -0.20 (below threshold)
    # -- but this test only checks the sign is threaded correctly when an
    # edge DOES clear, so use a bookmaker price that still produces a
    # positive edge against the new, lower true_prob.
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=3.00),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.50),
        ),
    )
    alerts = find_value_bets(falling_move, [game], [])
    assert len(alerts) == 1
    assert round(alerts[0].polymarket_relative_move, 6) == round((0.40 - 0.60) / 0.60, 6)
    assert alerts[0].polymarket_relative_move < 0


def test_one_bookmaker_with_no_match_does_not_block_the_other():
    unrelated_game = BookmakerGame(
        bookmaker="Novibet", event_name="SEA Seahawks vs ARI Cardinals",
        kickoff_time="2026-11-26T18:00:00+00:00",
        teams=(
            BookmakerTeamPrice(team_name="SEA Seahawks", decimal_odds=1.9),
            BookmakerTeamPrice(team_name="ARI Cardinals", decimal_odds=1.9),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [STALE_PADDYPOWER_GAME], [unrelated_game])
    assert len(alerts) == 1
    assert alerts[0].bookmaker == "Paddy Power"


def test_edge_exactly_at_threshold_is_excluded():
    # The spec's architecture is explicit: "edge > threshold", strictly
    # greater than, not >=. true_prob=0.60, decimal_odds=1.70 -> edge =
    # 1.70*0.60-1 = 0.02 exactly -> excluded.
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=1.70),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=2.00),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [game], [], min_edge=0.02)
    assert alerts == []


def test_edge_just_above_threshold_is_included():
    # true_prob=0.60, decimal_odds=1.71 -> edge = 1.71*0.60-1 = 0.026 (> 0.02)
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=1.71),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=2.00),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [game], [], min_edge=0.02)
    assert len(alerts) == 1


def test_edge_just_below_threshold_is_excluded():
    # true_prob=0.60, decimal_odds=1.69 -> edge = 1.69*0.60-1 = 0.014 (< 0.02)
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=1.69),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=2.00),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [game], [], min_edge=0.02)
    assert alerts == []


def test_no_games_in_either_list_returns_empty():
    assert find_value_bets(STALE_MOVE, [], []) == []


def test_opposite_team_leg_reveals_a_value_bet_the_tracked_leg_missed():
    """The flagship proof of this fix: Commanders' price FALLS (0.50->0.30),
    so Lions' implied probability correspondingly RISES (0.50->0.70). A
    bookmaker that hasn't repriced still offers both teams near their old
    ~50/50 prices. The tracked (Commanders) leg correctly shows no edge —
    but the untracked Lions leg is a real, large value bet that the old
    tracked-only design would never have found."""
    falling_commanders = MoveEvent(
        market_id="m4", question="Commanders vs. Lions", tracked_outcome="Commanders",
        old_price=0.50, new_price=0.30, relative_move=0.40,
        old_at=NOW, new_at=NOW, game_start_time="2026-08-22 16:00:00+00",
    )
    stale_game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Washington Commanders @ Detroit Lions",
        kickoff_time="2026-08-22T16:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Washington Commanders", decimal_odds=2.00),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=2.00),
        ),
    )

    alerts = find_value_bets(falling_commanders, [stale_game], [])

    assert len(alerts) == 1
    assert alerts[0].team_name == "Detroit Lions"
    assert round(alerts[0].edge, 6) == 0.40
    assert round(alerts[0].polymarket_old_price, 6) == 0.50
    assert round(alerts[0].polymarket_new_price, 6) == 0.70
    assert round(alerts[0].polymarket_relative_move, 6) == 0.40


def test_opposite_leg_old_and_new_prices_are_the_binary_complement():
    """Confirm the ValueBetAlert's Polymarket fields for the OPPOSITE
    team's leg show that team's own (derived) move, not the tracked
    team's move copied verbatim -- otherwise the notification would
    describe the wrong team's price history."""
    move = MoveEvent(
        market_id="m5", question="Bears vs. Lions", tracked_outcome="Bears",
        old_price=0.20, new_price=0.10, relative_move=0.50,
        old_at=NOW, new_at=NOW, game_start_time="2026-11-26 18:00:00+00",
    )
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=10.0),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.20),
        ),
    )
    alerts = find_value_bets(move, [game], [])

    lions_alerts = [a for a in alerts if a.team_name == "Detroit Lions"]
    assert len(lions_alerts) == 1
    lions = lions_alerts[0]
    assert round(lions.polymarket_old_price, 6) == 0.80   # 1 - 0.20
    assert round(lions.polymarket_new_price, 6) == 0.90   # 1 - 0.10
    assert round(lions.polymarket_relative_move, 6) == round((0.90 - 0.80) / 0.80, 6)


def test_tracked_old_price_of_one_does_not_crash_and_skips_opposite_leg():
    """Guards the division-by-zero edge case: if move.old_price is
    exactly 1.0, the opposite leg's derived old_price would be 0.0,
    which would divide-by-zero computing its relative move. The tracked
    leg must still work normally; the opposite leg must be silently
    skipped, never raise."""
    move = MoveEvent(
        market_id="m6", question="Bears vs. Lions", tracked_outcome="Bears",
        old_price=1.0, new_price=0.95, relative_move=0.05,
        old_at=NOW, new_at=NOW, game_start_time="2026-11-26 18:00:00+00",
    )
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=1.10),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=15.0),
        ),
    )
    alerts = find_value_bets(move, [game], [])  # must not raise
    assert all(a.team_name == "Chicago Bears" for a in alerts)
