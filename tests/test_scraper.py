from __future__ import annotations

import pytest

from paddypower_scraper.browser import BrowserFetchError
from paddypower_scraper.models import NFLGameOdds, TeamPrice
from paddypower_scraper.scraper import scrape_nfl_moneylines

GAME_A = NFLGameOdds(
    market_id="927.1", event_id="1", event_name="A @ B",
    kickoff_time="2026-08-21T00:00:00.000Z", competition_id=11432305,
    teams=(
        TeamPrice(team_name="A", selection_id=1, decimal_odds=2.0, home_or_away="AWAY"),
        TeamPrice(team_name="B", selection_id=2, decimal_odds=1.9, home_or_away="HOME"),
    ),
)
GAME_B = NFLGameOdds(
    market_id="927.2", event_id="2", event_name="C @ D",
    kickoff_time="2026-09-10T00:00:00.000Z", competition_id=12282733,
    teams=(
        TeamPrice(team_name="C", selection_id=3, decimal_odds=1.5, home_or_away="AWAY"),
        TeamPrice(team_name="D", selection_id=4, decimal_odds=2.5, home_or_away="HOME"),
    ),
)


class _FakeSession:
    def __init__(self, responses):
        self._responses = responses  # url -> dict or Exception
        self.fetched_urls = []

    def fetch_json(self, url, timeout_ms=20_000):
        self.fetched_urls.append(url)
        result = self._responses[url]
        if isinstance(result, Exception):
            raise result
        return result


def test_merges_games_from_both_competitions(monkeypatch):
    import paddypower_scraper.scraper as scraper_module

    monkeypatch.setattr(
        scraper_module, "parse_competition_page",
        lambda raw: [GAME_A] if raw == {"marker": "preseason"} else [GAME_B],
    )
    session = _FakeSession({
        "url-preseason": {"marker": "preseason"},
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "competition_page_url",
                        lambda cid: "url-preseason" if cid == 11432305 else "url-regular")

    games = scrape_nfl_moneylines(session, competition_ids=(11432305, 12282733))

    assert games == [GAME_A, GAME_B]
    assert session.fetched_urls == ["url-preseason", "url-regular"]


def test_one_competition_fetch_failure_does_not_block_the_other(monkeypatch):
    import paddypower_scraper.scraper as scraper_module

    monkeypatch.setattr(scraper_module, "parse_competition_page", lambda raw: [GAME_B])
    session = _FakeSession({
        "url-preseason": BrowserFetchError("url-preseason", "HTTP 404"),
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "competition_page_url",
                        lambda cid: "url-preseason" if cid == 11432305 else "url-regular")

    games = scrape_nfl_moneylines(session, competition_ids=(11432305, 12282733))

    assert games == [GAME_B]


def test_one_competition_parse_failure_does_not_block_the_other(monkeypatch):
    import paddypower_scraper.scraper as scraper_module

    def fake_parse(raw):
        if raw == {"marker": "preseason"}:
            # Simulates the real crash: a top-level shape parse_competition_page
            # doesn't expect (e.g. a list instead of a dict) blows up with
            # AttributeError on `raw.get(...)`.
            raise AttributeError("'list' object has no attribute 'get'")
        return [GAME_B]

    monkeypatch.setattr(scraper_module, "parse_competition_page", fake_parse)
    session = _FakeSession({
        "url-preseason": {"marker": "preseason"},
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "competition_page_url",
                        lambda cid: "url-preseason" if cid == 11432305 else "url-regular")

    games = scrape_nfl_moneylines(session, competition_ids=(11432305, 12282733))

    assert games == [GAME_B]


def test_default_competition_ids_are_preseason_and_regular_season():
    from paddypower_scraper.scraper import DEFAULT_COMPETITION_IDS
    assert DEFAULT_COMPETITION_IDS == (11432305, 12282733)
