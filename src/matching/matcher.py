"""Match a Polymarket NFL moneyline market to one bookmaker's game
listing, by unordered team pair + kickoff instant. Exact match only —
see this plan's Global Constraints for why."""

from __future__ import annotations

import re

from .models import BookmakerGame, BookmakerTeamPrice
from .teams import normalize_team_nickname
from .timeutil import to_instant

_VS_SPLIT = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)


def parse_polymarket_teams(question) -> "tuple[str, str] | None":
    """Extract both team nicknames from a Polymarket moneyline question
    like "Commanders vs. Lions" or "Lions vs Colts". Order is NOT
    meaningful — Polymarket's question field has no reliable home/away
    convention (verified against live data). Returns None if the
    question isn't in the expected two-team shape, or either half isn't
    a recognized NFL nickname."""
    if not isinstance(question, str):
        return None
    parts = _VS_SPLIT.split(question.strip())
    if len(parts) != 2:
        return None
    a = normalize_team_nickname(parts[0])
    b = normalize_team_nickname(parts[1])
    if a is None or b is None:
        return None
    return (a, b)


def match_game(
    polymarket_question: str,
    polymarket_kickoff,
    bookmaker_games: "list[BookmakerGame]",
) -> "BookmakerGame | None":
    """Match against ONE bookmaker's game list per call — callers match
    each bookmaker independently. Matches by unordered team pair +
    kickoff instant. Returns None if the question/kickoff don't parse,
    no game matches, or (never guess) more than one game matches."""
    teams = parse_polymarket_teams(polymarket_question)
    if teams is None:
        return None
    poly_instant = to_instant(polymarket_kickoff)
    if poly_instant is None:
        return None
    poly_pair = frozenset(teams)

    candidates = []
    for game in bookmaker_games:
        game_instant = to_instant(game.kickoff_time)
        if game_instant != poly_instant:
            continue
        n1 = normalize_team_nickname(game.teams[0].team_name)
        n2 = normalize_team_nickname(game.teams[1].team_name)
        if n1 is None or n2 is None:
            continue
        if frozenset((n1, n2)) == poly_pair:
            candidates.append(game)

    return candidates[0] if len(candidates) == 1 else None


def team_price_for(game: BookmakerGame, team_name: str) -> "BookmakerTeamPrice | None":
    """Look up one team's price within an already-matched game, by
    normalized nickname (accepts a bare nickname like "Raiders" or a full
    name like "Las Vegas Raiders" — both normalize the same way). None if
    not found or ambiguous."""
    target = normalize_team_nickname(team_name)
    if target is None:
        return None
    matches = [t for t in game.teams if normalize_team_nickname(t.team_name) == target]
    return matches[0] if len(matches) == 1 else None
