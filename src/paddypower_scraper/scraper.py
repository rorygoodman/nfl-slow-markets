from __future__ import annotations

import sys

from .api import NFL_COMPETITION_ID, NFL_PRESEASON_COMPETITION_ID, competition_page_url
from .browser import BrowserFetchError
from .models import NFLGameOdds
from .parsing import parse_competition_page

DEFAULT_COMPETITION_IDS = (NFL_PRESEASON_COMPETITION_ID, NFL_COMPETITION_ID)


def scrape_nfl_moneylines(
    session, competition_ids: tuple[int, ...] = DEFAULT_COMPETITION_IDS
) -> list[NFLGameOdds]:
    """Fetch + parse every open NFL moneyline market across the given
    competitions. A fetch failure for one competition is logged to stderr
    and does not block the others."""
    games: list[NFLGameOdds] = []
    for competition_id in competition_ids:
        url = competition_page_url(competition_id)
        try:
            raw = session.fetch_json(url)
        except BrowserFetchError as exc:
            print(f"paddypower_scraper: competition {competition_id} fetch failed: {exc}",
                  file=sys.stderr)
            continue
        games.extend(parse_competition_page(raw))
    return games
