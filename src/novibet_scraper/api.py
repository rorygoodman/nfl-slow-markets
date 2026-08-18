"""Novibet NFL endpoint constants and URL builder. No I/O."""

from __future__ import annotations

import time

# Fixed literal required by this endpoint family — meaning unclear (the
# same value appears in horsey-scraper's horse-racing feed URL in the same
# position, but it works unchanged for American Football here too), so
# treat it as an opaque required constant, not a per-sport id.
_LOCATION_ID = "4324"

NFL_PRESEASON_MARKET_VIEW_GROUP_ID = 5813718
NFL_MARKET_VIEW_GROUP_ID = 4799943

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
LOCALE = "en-IE"
TIMEZONE = "Europe/Dublin"

WARMUP_URL = "https://www.novibet.ie/sports/american-football/4372609/nfl/nfl/4374408"

API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "x-gw-domain-key": "_IE",
    "x-gw-cms-key": "_IE",
    "x-gw-application-name": "NoviIE",
    "x-gw-currency-sysname": "EUR",
    "x-gw-country-sysname": "IE",
    "x-gw-language-sysname": "en-IE",
    "x-gw-client-timezone": "Europe/Dublin",
    "x-gw-channel": "WebPC",
    "x-gw-client-layout": "Desktop",
    "x-gw-odds-representation": "Fractional",
}

_LOCATION_FEED_BASE = "https://www.novibet.ie/spt/feed/marketviews/location/v2"


def location_feed_url(market_view_group_id: int, timestamp_ms: "int | None" = None) -> str:
    """Build a location/v2 feed URL for the given NFL market-view group id."""
    ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    return (
        f"{_LOCATION_FEED_BASE}/{_LOCATION_ID}/{market_view_group_id}/"
        f"?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE&timestamp={ts}"
    )
