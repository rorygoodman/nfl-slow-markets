"""Match a Polymarket NFL moneyline market to one bookmaker's game
listing, by unordered team pair + kickoff instant within a small
tolerance window. See _KICKOFF_TOLERANCE below for why exact equality
isn't used."""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from .models import BookmakerGame, BookmakerTeamPrice
from .teams import normalize_team_nickname
from .timeutil import to_instant

logger = logging.getLogger("matching")

_VS_SPLIT = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)

# Covers real observed discrepancies between bookmakers' kickoff-time
# conventions (Paddy Power's Betfair-derived off-times, e.g. :01/:26/:31,
# vs Novibet's round times, e.g. :00/:15/:20/:25/:30/:35) — see this
# plan's final-review notes. Measured against real captured season data:
# the worst observed disagreement between the two bookmakers for the same
# real game was 5 minutes, so 30 minutes leaves a comfortable margin
# while staying tight enough to still be a meaningful "same kickoff"
# sanity check (kickoffs for different games are hours-to-days apart, and
# neither bookmaker ever lists the same team pair twice across a season).
_KICKOFF_TOLERANCE = timedelta(minutes=30)


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
    kickoff instant within _KICKOFF_TOLERANCE. Returns None if the
    question/kickoff don't parse, no game matches, or (never guess) more
    than one game matches."""
    teams = parse_polymarket_teams(polymarket_question)
    if teams is None:
        logger.debug(
            "match_game: rejected — Polymarket question did not parse into two teams: %r",
            polymarket_question,
        )
        return None
    poly_instant = to_instant(polymarket_kickoff)
    if poly_instant is None:
        logger.debug(
            "match_game: rejected — Polymarket kickoff did not parse: %r (question: %r)",
            polymarket_kickoff, polymarket_question,
        )
        return None
    poly_pair = frozenset(teams)

    candidates = []
    for game in bookmaker_games:
        game_instant = to_instant(game.kickoff_time)
        if game_instant is None or abs(game_instant - poly_instant) > _KICKOFF_TOLERANCE:
            continue
        n1 = normalize_team_nickname(game.teams[0].team_name)
        n2 = normalize_team_nickname(game.teams[1].team_name)
        if n1 is None or n2 is None:
            continue
        if frozenset((n1, n2)) == poly_pair:
            candidates.append(game)

    if len(candidates) == 0:
        logger.debug(
            "match_game: rejected — no bookmaker game matched team pair %s at %s (question: %r)",
            set(poly_pair), poly_instant, polymarket_question,
        )
        return None
    if len(candidates) > 1:
        logger.debug(
            "match_game: rejected — %d bookmaker games ambiguously matched team pair %s at %s "
            "(question: %r), refusing to guess",
            len(candidates), set(poly_pair), poly_instant, polymarket_question,
        )
        return None

    return candidates[0]


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
