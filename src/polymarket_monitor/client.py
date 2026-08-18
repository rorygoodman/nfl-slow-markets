from __future__ import annotations

import json

import httpx

from .models import MarketSnapshot

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
NFL_TAG_ID = 450


def fetch_nfl_moneyline_markets(client: httpx.Client | None = None) -> list[MarketSnapshot]:
    """Fetch every open NFL moneyline market's current sell-side (best-ask)
    price in a single request."""
    owns_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        response = http.get(
            GAMMA_MARKETS_URL,
            params={
                "tag_id": NFL_TAG_ID,
                "sports_market_types": "moneyline",
                "closed": "false",
                "limit": 100,
            },
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        snapshots = []
        for raw in payload:
            snapshot = _parse_market(raw)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots
    finally:
        if owns_client:
            http.close()


def _parse_market(raw: dict) -> MarketSnapshot | None:
    try:
        best_ask = raw.get("bestAsk")
        if best_ask is None:
            return None
        outcomes = json.loads(raw["outcomes"])
        if not outcomes:
            return None
        return MarketSnapshot(
            market_id=raw["id"],
            question=raw["question"],
            tracked_outcome=outcomes[0],
            best_ask=float(best_ask),
            game_start_time=raw.get("gameStartTime"),
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None
