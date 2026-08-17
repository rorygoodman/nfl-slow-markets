"""Opt-in live test against the real Polymarket Gamma API.

Run with: RUN_INTEGRATION=1 uv run pytest -m integration
Skipped by default — it needs network access."""

from __future__ import annotations

import os

import pytest

from polymarket_monitor.client import fetch_nfl_moneyline_markets

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="live network test; set RUN_INTEGRATION=1 to run",
)


@pytest.mark.integration
def test_fetches_at_least_one_open_nfl_moneyline_market():
    snapshots = fetch_nfl_moneyline_markets()
    assert snapshots, "expected at least one open NFL moneyline market"
    for snapshot in snapshots:
        assert snapshot.market_id
        assert snapshot.question
        assert snapshot.tracked_outcome
        assert 0.0 < snapshot.best_ask <= 1.0
