from __future__ import annotations

from .models import NFLGameOdds, TeamPrice

_MONEYLINE_BET_TYPE = "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW"


def parse_location_feed(raw, market_view_group_id: int) -> list[NFLGameOdds]:
    """Every fully-available NFL moneyline market in this location feed
    response, with both teams' current decimal odds."""
    if not isinstance(raw, list):
        return []
    out: list[NFLGameOdds] = []
    for location in raw:
        if not isinstance(location, dict):
            continue
        for bet_view in location.get("betViews") or []:
            if not isinstance(bet_view, dict):
                continue
            for item in bet_view.get("items") or []:
                game = _parse_item(item, market_view_group_id)
                if game is not None:
                    out.append(game)
    return out


def _parse_item(item, market_view_group_id: int) -> NFLGameOdds | None:
    try:
        captions = item["additionalCaptions"]
        competitor1 = captions["competitor1"]
        competitor2 = captions["competitor2"]
        if not isinstance(competitor1, str) or not competitor1:
            return None
        if not isinstance(competitor2, str) or not competitor2:
            return None
        event_id = str(item["eventBetContextId"])
        kickoff_time = item["startDate"]

        market = _find_moneyline_market(item.get("markets"))
        if market is None:
            return None

        team1 = _parse_bet_item(market["betItems"], "1", competitor1)
        team2 = _parse_bet_item(market["betItems"], "2", competitor2)
        if team1 is None or team2 is None:
            return None

        return NFLGameOdds(
            market_id=market["marketId"],
            event_id=event_id,
            event_name=f"{competitor1} vs {competitor2}",
            kickoff_time=kickoff_time,
            market_view_group_id=market_view_group_id,
            teams=(team1, team2),
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _find_moneyline_market(markets):
    if not isinstance(markets, list):
        return None
    for market in markets:
        if not isinstance(market, dict):
            continue
        if market.get("betTypeSysname") != _MONEYLINE_BET_TYPE:
            continue
        bet_items = market.get("betItems")
        if isinstance(bet_items, list) and len(bet_items) == 2:
            return market
    return None


def _parse_bet_item(bet_items, code: str, team_name: str) -> TeamPrice | None:
    for bet_item in bet_items:
        if not isinstance(bet_item, dict):
            continue
        if bet_item.get("code") != code:
            continue
        if not bet_item.get("isAvailable"):
            return None
        price = bet_item.get("price")
        bet_item_id = bet_item.get("id")
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            return None
        if not isinstance(bet_item_id, str) or not bet_item_id:
            return None
        return TeamPrice(team_name=team_name, selection_id=bet_item_id, decimal_odds=float(price))
    return None
