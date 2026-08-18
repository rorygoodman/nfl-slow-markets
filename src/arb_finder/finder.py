"""Join a detected Polymarket move to matched bookmaker prices, compute
the value-bet edge per leg, filter, and rank. See the design spec's
architecture diagram — this is the "-> per matched bookmaker leg: ...
edge = decimal_odds * true_prob - 1" step."""

from __future__ import annotations

from matching.matcher import match_game, team_price_for
from matching.models import BookmakerGame
from notifier.models import ValueBetAlert
from polymarket_monitor.models import MoveEvent

from .calculator import value_bet_edge

DEFAULT_MIN_EDGE = 0.02


def find_value_bets(
    move: MoveEvent,
    paddypower_games: "list[BookmakerGame]",
    novibet_games: "list[BookmakerGame]",
    min_edge: float = DEFAULT_MIN_EDGE,
) -> "list[ValueBetAlert]":
    """Check both bookmakers independently for a value-bet opportunity on
    the moved team. A bookmaker with no match, or an edge not strictly
    greater than `min_edge`, is silently skipped for that leg only —
    never an error, never blocks the other bookmaker. Results are ranked
    by edge descending."""
    alerts: "list[ValueBetAlert]" = []
    for games in (paddypower_games, novibet_games):
        alert = _find_leg(move, games)
        if alert is not None and alert.edge > min_edge:
            alerts.append(alert)
    alerts.sort(key=lambda a: a.edge, reverse=True)
    return alerts


def _find_leg(move: MoveEvent, bookmaker_games: "list[BookmakerGame]") -> "ValueBetAlert | None":
    game = match_game(move.question, move.game_start_time, bookmaker_games)
    if game is None:
        return None
    price = team_price_for(game, move.tracked_outcome)
    if price is None:
        return None

    true_prob = move.new_price
    # Round away binary floating-point representation noise (e.g.
    # 1.70*0.60-1 lands on 0.020000000000000018, not 0.02). 10 decimal
    # places is far finer than any real odds/probability value carries,
    # so this only strips artifacts of the arithmetic itself — it never
    # discards genuine precision, and it keeps `edge` exactly consistent
    # between what's compared against `min_edge` below and what's stored
    # on the returned alert.
    edge = round(value_bet_edge(price.decimal_odds, true_prob), 10)
    # MoveEvent.relative_move is an unsigned magnitude (see
    # polymarket_monitor/detector.py) — recompute it signed here, since
    # the notification needs to show direction. Division by move.old_price
    # is safe: MoveDetector guarantees old_price > 0 before ever
    # constructing a MoveEvent.
    signed_relative_move = round((move.new_price - move.old_price) / move.old_price, 10)

    return ValueBetAlert(
        game_name=move.question,
        team_name=price.team_name,
        bookmaker=game.bookmaker,
        decimal_odds=price.decimal_odds,
        polymarket_old_price=move.old_price,
        polymarket_new_price=move.new_price,
        polymarket_relative_move=signed_relative_move,
        edge=edge,
    )
