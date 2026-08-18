from __future__ import annotations

import sys

from .api import NFL_COMPETITION_ID, NFL_PRESEASON_COMPETITION_ID, competition_page_url
from .browser import BrowserFetchError
from .models import NFLGameOdds
from .parsing import parse_competition_page

DEFAULT_COMPETITION_IDS = (NFL_PRESEASON_COMPETITION_ID, NFL_COMPETITION_ID)


class AllCompetitionsFailedError(Exception):
    """Raised when every configured competition's fetch or parse step
    failed, i.e. an empty return value would be indistinguishable from a
    genuine no-games situation."""


def scrape_nfl_moneylines(
    session, competition_ids: tuple[int, ...] = DEFAULT_COMPETITION_IDS
) -> list[NFLGameOdds]:
    """Fetch + parse every open NFL moneyline market across the given
    competitions. A fetch failure or a parse failure for one competition is
    logged to stderr and does not block the others. Raises
    AllCompetitionsFailedError if every configured competition failed to
    fetch or parse, so callers can distinguish that from a legitimate
    zero-games result."""
    games: list[NFLGameOdds] = []
    succeeded = 0
    for competition_id in competition_ids:
        url = competition_page_url(competition_id)
        try:
            raw = session.fetch_json(url)
        except BrowserFetchError as exc:
            print(f"paddypower_scraper: competition {competition_id} fetch failed: {exc}",
                  file=sys.stderr)
            continue
        try:
            parsed = parse_competition_page(raw)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            print(f"paddypower_scraper: competition {competition_id} parse failed: {exc}",
                  file=sys.stderr)
            continue
        succeeded += 1
        games.extend(parsed)
    if competition_ids and succeeded == 0:
        raise AllCompetitionsFailedError(
            f"every configured competition failed to fetch or parse: {competition_ids}"
        )
    return games
