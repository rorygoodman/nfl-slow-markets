from __future__ import annotations

import httpx

from polymarket_monitor.client import _parse_market, fetch_nfl_moneyline_markets
from polymarket_monitor.models import MarketSnapshot

RAW_MARKET = {
    "id": "2869647",
    "question": "Raiders vs. Texans",
    "outcomes": '["Raiders", "Texans"]',
    "bestBid": 0.5,
    "bestAsk": 0.51,
    "gameStartTime": "2026-08-21 00:00:00+00",
    "closed": False,
}


def test_parses_a_valid_market():
    snapshot = _parse_market(RAW_MARKET)
    assert snapshot == MarketSnapshot(
        market_id="2869647",
        question="Raiders vs. Texans",
        tracked_outcome="Raiders",
        best_ask=0.51,
        game_start_time="2026-08-21 00:00:00+00",
    )


def test_returns_none_when_best_ask_missing():
    raw = {k: v for k, v in RAW_MARKET.items() if k != "bestAsk"}
    assert _parse_market(raw) is None


def test_returns_none_when_best_ask_is_null():
    raw = {**RAW_MARKET, "bestAsk": None}
    assert _parse_market(raw) is None


def test_returns_none_when_outcomes_is_malformed_json():
    raw = {**RAW_MARKET, "outcomes": "not json"}
    assert _parse_market(raw) is None


def test_returns_none_when_outcomes_is_empty_list():
    raw = {**RAW_MARKET, "outcomes": "[]"}
    assert _parse_market(raw) is None


def test_returns_none_when_required_field_missing():
    raw = {k: v for k, v in RAW_MARKET.items() if k != "id"}
    assert _parse_market(raw) is None


def test_game_start_time_defaults_to_none_when_absent():
    raw = {k: v for k, v in RAW_MARKET.items() if k != "gameStartTime"}
    snapshot = _parse_market(raw)
    assert snapshot is not None
    assert snapshot.game_start_time is None


class _StubHTTPClient:
    """Minimal stand-in for httpx.Client that returns a canned httpx.Response
    from .get() without making a real network call."""

    def __init__(self, response: httpx.Response):
        self._response = response

    def get(self, url, params=None):
        return self._response


def _fake_response(**kwargs) -> httpx.Response:
    """Build an httpx.Response with a request attached, so
    response.raise_for_status() behaves as it would for a real fetch."""
    request = httpx.Request("GET", "https://gamma-api.polymarket.com/markets")
    return httpx.Response(request=request, **kwargs)


def test_fetch_returns_parsed_snapshots_for_a_valid_list_response():
    response = _fake_response(status_code=200, json=[RAW_MARKET])
    client = _StubHTTPClient(response)

    snapshots = fetch_nfl_moneyline_markets(client)

    assert snapshots == [
        MarketSnapshot(
            market_id="2869647",
            question="Raiders vs. Texans",
            tracked_outcome="Raiders",
            best_ask=0.51,
            game_start_time="2026-08-21 00:00:00+00",
        )
    ]


def test_fetch_returns_empty_list_when_body_is_not_valid_json():
    response = _fake_response(status_code=200, content=b"<html>not json</html>")
    client = _StubHTTPClient(response)

    assert fetch_nfl_moneyline_markets(client) == []


def test_fetch_returns_empty_list_when_body_is_a_dict_not_a_list():
    response = _fake_response(status_code=200, json={"markets": [RAW_MARKET]})
    client = _StubHTTPClient(response)

    assert fetch_nfl_moneyline_markets(client) == []
