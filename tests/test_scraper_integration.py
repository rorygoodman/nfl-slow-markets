"""Opt-in live test against the real PaddyPower API (via a real headless
Chromium session — this is slow, ~10-20s, and needs network + the Chromium
browser installed via `uv run playwright install chromium`).

Run with: RUN_INTEGRATION=1 uv run pytest -m integration
Skipped by default."""

from __future__ import annotations

import os

import pytest

from paddypower_scraper.browser import BrowserSession
from paddypower_scraper.scraper import scrape_nfl_moneylines

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="live network + browser test; set RUN_INTEGRATION=1 to run",
)


@pytest.mark.integration
def test_scrapes_at_least_one_open_nfl_moneyline_market():
    with BrowserSession() as session:
        games = scrape_nfl_moneylines(session)
    assert games, "expected at least one open NFL moneyline market"
    for game in games:
        assert game.market_id
        assert len(game.teams) == 2
        for team in game.teams:
            assert team.decimal_odds > 1.0
