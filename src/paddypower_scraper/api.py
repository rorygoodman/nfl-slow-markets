"""PaddyPower NFL endpoint constants and URL builder. No I/O."""

from __future__ import annotations

APP_KEY = "vsd0Rm5ph2sS2uaK"
AMERICAN_FOOTBALL_EVENT_TYPE_ID = 6423

# Two distinct competitions on PaddyPower's side — querying only the
# regular-season one would silently miss every preseason game.
NFL_PRESEASON_COMPETITION_ID = 11432305
NFL_COMPETITION_ID = 12282733

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
LOCALE = "en-GB"
TIMEZONE = "Europe/Dublin"

WARMUP_URL = "https://www.paddypower.com/american-football"

_COMPETITION_PAGE_BASE = (
    "https://apisms.paddypower.com/smspp/competition-page/v3"
    f"?_ak={APP_KEY}&betexRegion=IRL&capiJurisdiction=intl"
    "&countryCode=IE&currencyCode=EUR"
    f"&eventTypeId={AMERICAN_FOOTBALL_EVENT_TYPE_ID}&exchangeLocale=en_GB"
    "&includeBadges=true&includeLayout=true&includePrices=true"
    "&includeSeoCards=true&includeSeoFooter=true&language=en"
    "&loggedIn=false&regionCode=IRE"
)


def competition_page_url(competition_id: int) -> str:
    """Build a competition-page/v3 URL for the given NFL competition id."""
    return f"{_COMPETITION_PAGE_BASE}&competitionId={competition_id}"
