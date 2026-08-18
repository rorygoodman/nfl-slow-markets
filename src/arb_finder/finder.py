"""Join a detected Polymarket move to matched bookmaker prices, compute
the value-bet edge per leg, filter, and rank. See the design spec's
architecture diagram — this is the "-> per matched bookmaker leg: ...
edge = decimal_odds * true_prob - 1" step.

Checks BOTH teams in the market, not just the one Polymarket's API
happened to list first (`move.tracked_outcome`). When the tracked
team's price falls, the real value bet is usually on the OTHER team,
whose price rose correspondingly — that leg would otherwise never be
checked at all."""

from __future__ import annotations

from matching.matcher import match_game, parse_polymarket_teams, team_price_for
from matching.models import BookmakerGame
from matching.teams import normalize_team_nickname
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
    """Check both teams in the market, against both bookmakers,
    independently. A bookmaker with no match, or an edge not strictly
    greater than `min_edge`, is silently skipped for that leg only —
    never an error, never blocks any other leg. Results are ranked by
    edge descending."""
    alerts: "list[ValueBetAlert]" = []
    for team_name, old_price, new_price in _both_team_references(move):
        for games in (paddypower_games, novibet_games):
            alert = _find_leg(move, games, team_name, old_price, new_price)
            if alert is not None and alert.edge > min_edge:
                alerts.append(alert)
    alerts.sort(key=lambda a: a.edge, reverse=True)
    return alerts


def _both_team_references(move: MoveEvent) -> "list[tuple[str, float, float]]":
    """The tracked team's reference prices are Polymarket's own observed
    old/new prices. The opposite team's reference prices are derived as
    the binary-market complement (1 - tracked price) — approximate but
    conservative (see module docstring). Falls back to tracked-only if
    the question can't be parsed into two recognized teams."""
    teams = parse_polymarket_teams(move.question)
    tracked_nick = normalize_team_nickname(move.tracked_outcome)
    tracked_reference = (move.tracked_outcome, move.old_price, move.new_price)
    if teams is None or tracked_nick not in teams:
        return [tracked_reference]

    opposite_nick = teams[1] if teams[0] == tracked_nick else teams[0]
    references = [tracked_reference]
    opposite_old = 1.0 - move.old_price
    if opposite_old > 0:
        # Guards div-by-zero in _find_leg's relative-move calc for the
        # (extremely unlikely) case of a tracked old_price of exactly 1.0.
        references.append((opposite_nick, opposite_old, 1.0 - move.new_price))
    return references


def _find_leg(
    move: MoveEvent,
    bookmaker_games: "list[BookmakerGame]",
    team_name: str,
    old_price: float,
    new_price: float,
) -> "ValueBetAlert | None":
    game = match_game(move.question, move.game_start_time, bookmaker_games)
    if game is None:
        return None
    price = team_price_for(game, team_name)
    if price is None:
        return None

    true_prob = new_price
    edge = value_bet_edge(price.decimal_odds, true_prob)
    # Rounded to strip IEEE-754 representation noise (e.g. 1.70*0.60-1 ==
    # 0.020000000000000018, not 0.02) — 10 decimal places is ~8 orders of
    # magnitude finer than any real odds/probability precision, so no
    # genuine precision is lost; this only removes floating-point
    # artifacts that would otherwise corrupt exact-boundary comparisons.
    signed_relative_move = round((new_price - old_price) / old_price, 10)

    return ValueBetAlert(
        game_name=move.question,
        team_name=price.team_name,
        bookmaker=game.bookmaker,
        decimal_odds=price.decimal_odds,
        polymarket_old_price=round(old_price, 10),
        polymarket_new_price=round(new_price, 10),
        polymarket_relative_move=signed_relative_move,
        edge=round(edge, 10),
    )
