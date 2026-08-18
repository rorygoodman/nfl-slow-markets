from __future__ import annotations

import json
from pathlib import Path

from novibet_scraper.models import NFLGameOdds, TeamPrice
from novibet_scraper.parsing import parse_location_feed

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "novibet_location_feed_sample.json"


def _load_fixture() -> list:
    return json.loads(FIXTURE_PATH.read_text())


def test_parses_the_one_fully_available_moneyline_market():
    games = parse_location_feed(_load_fixture(), market_view_group_id=5813718)

    assert len(games) == 1
    game = games[0]
    assert game == NFLGameOdds(
        market_id=1709836937,
        event_id="47678025",
        event_name="HOU Texans vs LV Raiders",
        kickoff_time="2026-08-21T00:00:00+00:00",
        market_view_group_id=5813718,
        teams=(
            TeamPrice(team_name="HOU Texans", selection_id="7127413176", decimal_odds=1.78),
            TeamPrice(team_name="LV Raiders", selection_id="7127413177", decimal_odds=2.0),
        ),
    )


def test_skips_game_when_one_side_is_unavailable():
    games = parse_location_feed(_load_fixture(), market_view_group_id=5813718)
    assert all(g.event_id != "47678099" for g in games)


def test_returns_empty_list_for_empty_input():
    assert parse_location_feed([], market_view_group_id=5813718) == []


def test_returns_empty_list_when_top_level_is_not_a_list():
    assert parse_location_feed({"not": "a list"}, market_view_group_id=5813718) == []


def test_skips_item_missing_competitor_names():
    raw = [{
        "betViews": [{
            "items": [{
                "eventBetContextId": 1,
                "additionalCaptions": {},
                "startDate": "2026-01-01T00:00:00+00:00",
                "markets": [{
                    "marketId": 1,
                    "betTypeSysname": "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW",
                    "betItems": [
                        {"id": "1", "code": "1", "price": 1.5, "isAvailable": True},
                        {"id": "2", "code": "2", "price": 2.5, "isAvailable": True},
                    ],
                }],
            }],
        }],
    }]
    assert parse_location_feed(raw, market_view_group_id=1) == []


def test_skips_item_with_no_moneyline_market():
    raw = [{
        "betViews": [{
            "items": [{
                "eventBetContextId": 1,
                "additionalCaptions": {"competitor1": "A", "competitor2": "B"},
                "startDate": "2026-01-01T00:00:00+00:00",
                "markets": [{
                    "marketId": 1,
                    "betTypeSysname": "AMERICAN_FOOTBALL_UNDER_OVER",
                    "betItems": [
                        {"id": "1", "code": "O", "price": 1.5, "isAvailable": True},
                        {"id": "2", "code": "U", "price": 2.5, "isAvailable": True},
                    ],
                }],
            }],
        }],
    }]
    assert parse_location_feed(raw, market_view_group_id=1) == []


def test_skips_market_entry_that_is_none():
    raw = [{
        "betViews": [{
            "items": [{
                "eventBetContextId": 1,
                "additionalCaptions": {"competitor1": "A", "competitor2": "B"},
                "startDate": "2026-01-01T00:00:00+00:00",
                "markets": [None, {
                    "marketId": 1,
                    "betTypeSysname": "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW",
                    "betItems": [
                        {"id": "1", "code": "1", "price": 1.5, "isAvailable": True},
                        {"id": "2", "code": "2", "price": 2.5, "isAvailable": True},
                    ],
                }],
            }],
        }],
    }]
    games = parse_location_feed(raw, market_view_group_id=1)
    assert len(games) == 1
