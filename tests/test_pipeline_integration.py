"""Opt-in live test: runs pipeline.main() against a real live Polymarket
snapshot and real Paddy Power / Novibet scrapes end-to-end (parsing,
scraping, matching, edge calculation). send_notification is
monkeypatched to a no-op recorder so this never sends a real push, per
the project's test-suite constraint (design spec's Testing section) —
only the notify step is stubbed; everything upstream (scrape, match,
arb) runs for real against live data.

Requires real network/Playwright access and a valid
~/.nfl-slow-markets/credentials.json (see common.credentials) — same
environment assumption as every other live scraper integration test in
this repo.

Run with: RUN_INTEGRATION=1 uv run pytest -m integration"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from orchestrator import pipeline
from orchestrator.serialization import move_event_to_json
from polymarket_monitor.client import fetch_nfl_moneyline_markets
from polymarket_monitor.models import MoveEvent

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="live network test; set RUN_INTEGRATION=1 to run",
)


@pytest.mark.integration
def test_pipeline_runs_end_to_end_against_live_data(monkeypatch, tmp_path):
    snapshots = fetch_nfl_moneyline_markets()
    assert snapshots, "expected at least one open NFL moneyline market to build a test event from"
    snapshot = snapshots[0]

    now = datetime.now(timezone.utc)
    old_price = snapshot.best_ask * 0.9
    move = MoveEvent(
        market_id=snapshot.market_id,
        question=snapshot.question,
        tracked_outcome=snapshot.tracked_outcome,
        old_price=old_price,
        new_price=snapshot.best_ask,
        relative_move=abs(snapshot.best_ask - old_price) / old_price,
        old_at=now - timedelta(minutes=10),
        new_at=now,
        game_start_time=snapshot.game_start_time,
    )

    sent = []
    monkeypatch.setattr(
        pipeline, "send_notification", lambda message, topic: sent.append(message) or True
    )
    monkeypatch.setattr(pipeline, "default_cooldown_path", lambda: tmp_path / "cooldown.json")

    result = pipeline.main([move_event_to_json(move)])

    assert result == 0
