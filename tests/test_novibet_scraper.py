from __future__ import annotations

import pytest

from novibet_scraper.browser import BrowserFetchError
from novibet_scraper.models import NFLGameOdds, TeamPrice
from novibet_scraper.scraper import (
    AllMarketViewGroupsFailedError,
    scrape_nfl_moneylines,
)

GAME_A = NFLGameOdds(
    market_id=1, event_id="1", event_name="A vs B",
    kickoff_time="2026-08-21T00:00:00+00:00", market_view_group_id=5813718,
    teams=(
        TeamPrice(team_name="A", selection_id="1", decimal_odds=2.0),
        TeamPrice(team_name="B", selection_id="2", decimal_odds=1.9),
    ),
)
GAME_B = NFLGameOdds(
    market_id=2, event_id="2", event_name="C vs D",
    kickoff_time="2026-09-10T00:00:00+00:00", market_view_group_id=4799943,
    teams=(
        TeamPrice(team_name="C", selection_id="3", decimal_odds=1.5),
        TeamPrice(team_name="D", selection_id="4", decimal_odds=2.5),
    ),
)


class _FakeSession:
    def __init__(self, responses):
        self._responses = responses  # url -> value or Exception
        self.fetched_urls = []

    def fetch_json(self, url, timeout_ms=20_000):
        self.fetched_urls.append(url)
        result = self._responses[url]
        if isinstance(result, Exception):
            raise result
        return result


def test_merges_games_from_both_market_view_groups(monkeypatch):
    import novibet_scraper.scraper as scraper_module

    monkeypatch.setattr(
        scraper_module, "parse_location_feed",
        lambda raw, group_id: [GAME_A] if raw == {"marker": "preseason"} else [GAME_B],
    )
    session = _FakeSession({
        "url-preseason": {"marker": "preseason"},
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "location_feed_url",
                        lambda group_id: "url-preseason" if group_id == 5813718 else "url-regular")

    games = scrape_nfl_moneylines(session, market_view_group_ids=(5813718, 4799943))

    assert games == [GAME_A, GAME_B]
    assert session.fetched_urls == ["url-preseason", "url-regular"]


def test_one_group_fetch_failure_does_not_block_the_other(monkeypatch):
    import novibet_scraper.scraper as scraper_module

    monkeypatch.setattr(scraper_module, "parse_location_feed", lambda raw, group_id: [GAME_B])
    session = _FakeSession({
        "url-preseason": BrowserFetchError("url-preseason", "HTTP 404"),
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "location_feed_url",
                        lambda group_id: "url-preseason" if group_id == 5813718 else "url-regular")

    games = scrape_nfl_moneylines(session, market_view_group_ids=(5813718, 4799943))

    assert games == [GAME_B]


def test_one_group_parse_failure_does_not_block_the_other(monkeypatch):
    import novibet_scraper.scraper as scraper_module

    def fake_parse(raw, group_id):
        if raw == {"marker": "preseason"}:
            raise AttributeError("boom")
        return [GAME_B]

    monkeypatch.setattr(scraper_module, "parse_location_feed", fake_parse)
    session = _FakeSession({
        "url-preseason": {"marker": "preseason"},
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "location_feed_url",
                        lambda group_id: "url-preseason" if group_id == 5813718 else "url-regular")

    games = scrape_nfl_moneylines(session, market_view_group_ids=(5813718, 4799943))

    assert games == [GAME_B]


def test_raises_when_every_group_fetch_fails(monkeypatch):
    import novibet_scraper.scraper as scraper_module

    session = _FakeSession({
        "url-preseason": BrowserFetchError("url-preseason", "HTTP 404"),
        "url-regular": BrowserFetchError("url-regular", "HTTP 500"),
    })
    monkeypatch.setattr(scraper_module, "location_feed_url",
                        lambda group_id: "url-preseason" if group_id == 5813718 else "url-regular")

    with pytest.raises(AllMarketViewGroupsFailedError):
        scrape_nfl_moneylines(session, market_view_group_ids=(5813718, 4799943))


def test_raises_when_every_group_parse_fails(monkeypatch):
    import novibet_scraper.scraper as scraper_module

    def fake_parse(raw, group_id):
        raise AttributeError("boom")

    monkeypatch.setattr(scraper_module, "parse_location_feed", fake_parse)
    session = _FakeSession({
        "url-preseason": {"marker": "preseason"},
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "location_feed_url",
                        lambda group_id: "url-preseason" if group_id == 5813718 else "url-regular")

    with pytest.raises(AllMarketViewGroupsFailedError):
        scrape_nfl_moneylines(session, market_view_group_ids=(5813718, 4799943))


def test_does_not_raise_when_one_group_succeeds_with_zero_games(monkeypatch):
    import novibet_scraper.scraper as scraper_module

    monkeypatch.setattr(scraper_module, "parse_location_feed", lambda raw, group_id: [])
    session = _FakeSession({
        "url-preseason": {"marker": "preseason"},
        "url-regular": {"marker": "regular"},
    })
    monkeypatch.setattr(scraper_module, "location_feed_url",
                        lambda group_id: "url-preseason" if group_id == 5813718 else "url-regular")

    games = scrape_nfl_moneylines(session, market_view_group_ids=(5813718, 4799943))

    assert games == []


def test_default_market_view_group_ids_are_preseason_and_regular_season():
    from novibet_scraper.scraper import DEFAULT_MARKET_VIEW_GROUP_IDS
    assert DEFAULT_MARKET_VIEW_GROUP_IDS == (5813718, 4799943)
