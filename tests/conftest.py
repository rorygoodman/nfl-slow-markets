"""Shared pytest fixtures for paddypower_scraper tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


@pytest.fixture
def competition_page_payload() -> dict:
    """Real captured competition-page/v3 shape: one valid open moneyline
    market, one non-moneyline market, one suspended moneyline market."""
    return _load("paddypower_competition_page_sample.json")
