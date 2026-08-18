from __future__ import annotations

from .models import NFLGameOdds, TeamPrice


def parse_competition_page(raw: dict) -> list[NFLGameOdds]:
    """Every open NFL moneyline market on this competition page, with both
    teams' current decimal odds."""
    attachments = raw.get("attachments", {})
    events = attachments.get("events", {})
    markets = attachments.get("markets", {})
    out: list[NFLGameOdds] = []
    for market in markets.values():
        game = _parse_market(market, events)
        if game is not None:
            out.append(game)
    return out


def _parse_market(market: dict, events: dict) -> NFLGameOdds | None:
    try:
        if market.get("marketType") != "MONEY_LINE":
            return None
        if market.get("marketStatus") != "OPEN":
            return None
        if market.get("numberOfRunners") != 2:
            return None
        event = events.get(str(market["eventId"]))
        if event is None:
            return None
        runners = market["runners"]
        if len(runners) != 2:
            return None
        team_a = _parse_runner(runners[0])
        team_b = _parse_runner(runners[1])
        if team_a is None or team_b is None:
            return None
        return NFLGameOdds(
            market_id=market["marketId"],
            event_id=str(market["eventId"]),
            event_name=event["name"],
            kickoff_time=event["openDate"],
            competition_id=market["competitionId"],
            teams=(team_a, team_b),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_runner(runner: dict) -> TeamPrice | None:
    try:
        if runner.get("runnerStatus") != "ACTIVE":
            return None
        decimal_odds = runner["winRunnerOdds"]["trueOdds"]["decimalOdds"]["decimalOdds"]
        return TeamPrice(
            team_name=runner["runnerName"],
            selection_id=runner["selectionId"],
            decimal_odds=float(decimal_odds),
            home_or_away=runner["result"]["type"],
        )
    except (KeyError, TypeError, ValueError):
        return None
