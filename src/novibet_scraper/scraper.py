from __future__ import annotations

import sys

from .api import (
    NFL_MARKET_VIEW_GROUP_ID,
    NFL_PRESEASON_MARKET_VIEW_GROUP_ID,
    location_feed_url,
)
from .browser import BrowserFetchError
from .models import NFLGameOdds
from .parsing import parse_location_feed

DEFAULT_MARKET_VIEW_GROUP_IDS = (NFL_PRESEASON_MARKET_VIEW_GROUP_ID, NFL_MARKET_VIEW_GROUP_ID)


class AllMarketViewGroupsFailedError(Exception):
    """Raised when every configured market-view group failed (fetch or
    parse) — signals a total scrape failure, as opposed to a legitimate
    zero-games result (e.g. off-season)."""


def scrape_nfl_moneylines(
    session, market_view_group_ids: tuple[int, ...] = DEFAULT_MARKET_VIEW_GROUP_IDS
) -> list[NFLGameOdds]:
    """Fetch + parse every fully-available NFL moneyline market across the
    given market-view groups. A fetch failure or a parse failure for one
    group is logged to stderr and does not block the others. Raises
    AllMarketViewGroupsFailedError only if every configured group failed
    (fetch or parse) — a group that legitimately returns zero games is not
    a failure."""
    games: list[NFLGameOdds] = []
    succeeded = 0
    for group_id in market_view_group_ids:
        url = location_feed_url(group_id)
        try:
            raw = session.fetch_json(url)
        except BrowserFetchError as exc:
            print(f"novibet_scraper: market view group {group_id} fetch failed: {exc}",
                  file=sys.stderr)
            continue
        try:
            parsed = parse_location_feed(raw, group_id)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            print(f"novibet_scraper: market view group {group_id} parse failed: {exc}",
                  file=sys.stderr)
            continue
        games.extend(parsed)
        succeeded += 1

    if market_view_group_ids and succeeded == 0:
        raise AllMarketViewGroupsFailedError(
            f"all {len(market_view_group_ids)} configured market view group(s) failed"
        )
    return games
