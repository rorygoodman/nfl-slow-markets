# PaddyPower NFL Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `paddypower_scraper` module — a standalone component that fetches Paddy Power's current NFL moneyline (game-winner) odds for both the preseason and regular-season competitions, via the same Cloudflare-gated headless-Chromium approach already proven in the sibling `horsey-scraper` project's `paddypower_scraper`.

**Architecture:** A pure-logic `parsing.py` turns Paddy Power's `competition-page/v3` JSON into `NFLGameOdds` objects (team names, decimal odds, kickoff time) — no I/O, fully unit-testable against real captured fixture data. A `BrowserSession` (Playwright headless Chromium, copied from `horsey-scraper`'s proven pattern) warms up on paddypower.com to earn a `cf_clearance` cookie, then does in-page `fetch()` calls against the API — a plain `curl`/`requests` call gets Cloudflare-blocked (verified live during this plan's research: 403 "Just a moment..." challenge, even with a real session's cookies replayed, because Cloudflare's managed challenge also checks the TLS/JA3 fingerprint, which only a real browser presents). `scraper.py` orchestrates: fetch each configured competition ID, parse, merge, with a fetch failure in one competition non-fatal to the others. `__main__.py` writes the result to `paddypower_nfl.json`.

**Tech Stack:** Python ≥3.11, `uv`, `playwright>=1.42` (headless Chromium), `pytest` — matching `horsey-scraper`'s existing scraper stack exactly.

**Spec:** `docs/superpowers/specs/2026-08-17-nfl-slow-markets-design.md`

## Global Constraints

- Python ≥3.11, managed with `uv`.
- Decimal odds only — Paddy Power's API already returns decimal odds (`winRunnerOdds.trueOdds.decimalOdds.decimalOdds`), matching the spec's `value_bet_edge(decimal_odds, true_prob)` formula directly. No fractional-to-decimal conversion needed.
- **Never hardcode, log, or commit any session cookie, `cf_clearance` value, or other credential.** This plan's research used cookies pasted directly by the user from their own browser session for API-discovery purposes only — none of that data appears in this plan's code. The implementation must derive its own Cloudflare clearance at runtime via a live Playwright warmup (`BrowserSession`, Task 2), exactly like `horsey-scraper`'s existing `paddypower_scraper.browser.BrowserSession` — never by replaying a stored cookie value.
- Non-fatal per-competition error handling: a fetch failure for one competition ID (e.g. the preseason competition disappearing once the season starts) must not prevent scraping the other configured competition ID.
- No credentials file needed — Paddy Power's odds pages are public, unauthenticated (matching how `horsey-scraper`'s existing `paddypower_scraper` already works).
- Read-only: only HTTP GET requests (via in-page `fetch()`), no order/bet placement anywhere in this module.
- This plan covers `paddypower_scraper` only. Team/game matching against Polymarket, the value-bet edge calculation, bet365 scraping, and email notification are separate follow-up plans per the spec's subsystem list.

---

## Verified live API details (checked against the real Paddy Power API on 2026-08-18)

- **Endpoint:** `GET https://apisms.paddypower.com/smspp/competition-page/v3` with query params `_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl&competitionId={ID}&countryCode=IE&currencyCode=EUR&eventTypeId=6423&exchangeLocale=en_GB&includeBadges=true&includeLayout=true&includePrices=true&includeSeoCards=true&includeSeoFooter=true&language=en&loggedIn=false&regionCode=IRE`. `eventTypeId=6423` is American Football (confirmed from the response's own `attachments.eventTypes` field). `_ak` is the same app key `horsey-scraper`'s racing scraper already uses.
- **Two distinct competition IDs are needed, not one:**
  - `11432305` — "NFL Preseason Matches" (confirmed live: contains Raiders @ Texans, 49ers @ Chargers, and 12 other Aug 21-24 2026 preseason games — matches the live Polymarket preseason markets found while building the `polymarket_monitor` plan almost exactly: Raiders @ Texans both show `2026-08-21T00:00:00.000Z` kickoff).
  - `12282733` — "NFL" (the regular season; confirmed live, earliest event `2026-09-10`). A market lookup against only this ID would silently miss every preseason game — the entire point of this tool right now.
  - The scraper queries **both** by default (configurable), so it keeps working once the regular season starts without a code change.
- **Response shape:** a `competition-page/v3` response is `{"layout": {...}, "attachments": {"eventTypes": {...}, "competitions": {...}, "events": {<eventId>: {...}}, "markets": {<marketId>: {...}}}}`. `events` and `markets` are dicts keyed by string ID, not arrays.
  - Event object: `{eventId, name (e.g. "Las Vegas Raiders @ Houston Texans", format "Away @ Home"), eventTypeId, competitionId, countryCode, openDate (ISO 8601 UTC), videoAvailable}`.
  - Market object (confirmed real, complete example below — Chicago Bears @ Detroit Lions): `{marketId, eventTypeId, competitionId, eventId, marketName, marketTime, marketType, numberOfRunners, marketStatus, runners: [{selectionId, runnerName, result: {type: "HOME"|"AWAY"}, runnerStatus, winRunnerOdds: {trueOdds: {decimalOdds: {decimalOdds: <float>}}}}, ...]}`.
  - `marketType` is the reliable machine-readable filter for "moneyline" — `marketName` varies between `"Match Betting"` and `"Moneyline"` for the same market type, so filter on `marketType == "MONEY_LINE"` instead.
  - `marketStatus` is `"OPEN"` for a live, bettable market — confirmed other values exist (suspended markets) so this must be filtered.
  - Use `winRunnerOdds.trueOdds.decimalOdds.decimalOdds` (the precise figure), not `decimalDisplayOdds` (a separately-rounded display value) — confirmed both exist in the real payload; `trueOdds` is the one to use for a value-bet calculation.
- **`WARMUP_URL`:** `https://www.paddypower.com/american-football` — a real URL observed directly in the API's own SEO-text response content (`<a href="https://www.paddypower.com/american-football">American Football odds</a>`), not a guess. Loading any page on the site earns the Cloudflare clearance cookie needed for subsequent same-origin `fetch()` calls, matching `horsey-scraper`'s existing warmup pattern (which uses `/horse-racing` for the same reason).

---

### Task 1: Domain models + pure parsing logic (TDD, fixture-based)

**Files:**
- Create: `src/paddypower_scraper/__init__.py`
- Create: `src/paddypower_scraper/models.py`
- Create: `src/paddypower_scraper/parsing.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/paddypower_competition_page_sample.json`
- Test: `tests/test_parsing.py`

**Interfaces:**
- Produces (used by Task 3):
  - `models.TeamPrice(team_name: str, selection_id: int, decimal_odds: float, home_or_away: str)`
  - `models.NFLGameOdds(market_id: str, event_id: str, event_name: str, kickoff_time: str, competition_id: int, teams: tuple[TeamPrice, TeamPrice])`
  - `parsing.parse_competition_page(raw: dict) -> list[NFLGameOdds]`

- [ ] **Step 1: Create the fixture file**

`tests/fixtures/paddypower_competition_page_sample.json` — a real, captured `competition-page/v3` payload trimmed to its `attachments.events`/`attachments.markets` shape, covering three cases: one valid open moneyline market with real odds, one non-moneyline market (must be filtered out), one suspended moneyline market (must be filtered out):

```json
{
  "attachments": {
    "events": {
      "35607159": {
        "eventId": 35607159,
        "name": "Chicago Bears @ Detroit Lions",
        "eventTypeId": 6423,
        "competitionId": 12282733,
        "countryCode": "GB",
        "openDate": "2026-11-26T18:00:00.000Z",
        "videoAvailable": false
      },
      "35950163": {
        "eventId": 35950163,
        "name": "Atlanta Falcons @ Indianapolis Colts",
        "eventTypeId": 6423,
        "competitionId": 11432305,
        "countryCode": "GB",
        "openDate": "2026-08-22T17:00:00.000Z",
        "videoAvailable": false
      }
    },
    "markets": {
      "927.383543353": {
        "marketId": "927.383543353",
        "eventTypeId": 6423,
        "competitionId": 12282733,
        "eventId": 35607159,
        "marketName": "Match Betting",
        "marketTime": "2026-11-26T18:00:00.000Z",
        "marketType": "MONEY_LINE",
        "numberOfRunners": 2,
        "marketStatus": "OPEN",
        "runners": [
          {
            "selectionId": 50194,
            "runnerName": "Chicago Bears",
            "result": {"type": "AWAY"},
            "runnerStatus": "ACTIVE",
            "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 2.1}}}
          },
          {
            "selectionId": 50193,
            "runnerName": "Detroit Lions",
            "result": {"type": "HOME"},
            "runnerStatus": "ACTIVE",
            "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.727272727272727}}}
          }
        ]
      },
      "927.900000001": {
        "marketId": "927.900000001",
        "eventTypeId": 6423,
        "competitionId": 11432305,
        "eventId": 35950163,
        "marketName": "Total Points",
        "marketTime": "2026-08-22T17:00:00.000Z",
        "marketType": "TOTAL_POINTS",
        "numberOfRunners": 2,
        "marketStatus": "OPEN",
        "runners": []
      },
      "927.900000002": {
        "marketId": "927.900000002",
        "eventTypeId": 6423,
        "competitionId": 11432305,
        "eventId": 35950163,
        "marketName": "Moneyline",
        "marketTime": "2026-08-22T17:00:00.000Z",
        "marketType": "MONEY_LINE",
        "numberOfRunners": 2,
        "marketStatus": "SUSPENDED",
        "runners": [
          {
            "selectionId": 50300,
            "runnerName": "Atlanta Falcons",
            "result": {"type": "AWAY"},
            "runnerStatus": "ACTIVE",
            "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}
          },
          {
            "selectionId": 50301,
            "runnerName": "Indianapolis Colts",
            "result": {"type": "HOME"},
            "runnerStatus": "ACTIVE",
            "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}
          }
        ]
      }
    }
  }
}
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 3: Write the failing tests for `parse_competition_page`**

`tests/test_parsing.py`:

```python
from __future__ import annotations

from paddypower_scraper.models import NFLGameOdds, TeamPrice
from paddypower_scraper.parsing import parse_competition_page


def test_parses_the_one_valid_open_moneyline_market(competition_page_payload):
    games = parse_competition_page(competition_page_payload)
    assert len(games) == 1
    game = games[0]
    assert game == NFLGameOdds(
        market_id="927.383543353",
        event_id="35607159",
        event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        competition_id=12282733,
        teams=(
            TeamPrice(team_name="Chicago Bears", selection_id=50194,
                      decimal_odds=2.1, home_or_away="AWAY"),
            TeamPrice(team_name="Detroit Lions", selection_id=50193,
                      decimal_odds=1.727272727272727, home_or_away="HOME"),
        ),
    )


def test_skips_non_moneyline_markets(competition_page_payload):
    games = parse_competition_page(competition_page_payload)
    assert all(g.market_id != "927.900000001" for g in games)


def test_skips_suspended_moneyline_markets(competition_page_payload):
    games = parse_competition_page(competition_page_payload)
    assert all(g.market_id != "927.900000002" for g in games)


def test_returns_empty_list_for_no_markets():
    assert parse_competition_page({"attachments": {"events": {}, "markets": {}}}) == []


def test_skips_market_with_missing_event():
    raw = {
        "attachments": {
            "events": {},
            "markets": {
                "927.1": {
                    "marketId": "927.1", "eventId": 999, "competitionId": 1,
                    "marketType": "MONEY_LINE", "marketStatus": "OPEN",
                    "numberOfRunners": 2,
                    "runners": [
                        {"selectionId": 1, "runnerName": "A", "result": {"type": "AWAY"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 2.0}}}},
                        {"selectionId": 2, "runnerName": "B", "result": {"type": "HOME"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}},
                    ],
                }
            },
        }
    }
    assert parse_competition_page(raw) == []


def test_skips_runner_missing_odds():
    raw = {
        "attachments": {
            "events": {"1": {"eventId": 1, "name": "A @ B", "openDate": "2026-01-01T00:00:00.000Z"}},
            "markets": {
                "927.1": {
                    "marketId": "927.1", "eventId": 1, "competitionId": 1,
                    "marketType": "MONEY_LINE", "marketStatus": "OPEN",
                    "numberOfRunners": 2,
                    "runners": [
                        {"selectionId": 1, "runnerName": "A", "result": {"type": "AWAY"},
                         "runnerStatus": "ACTIVE", "winRunnerOdds": {}},
                        {"selectionId": 2, "runnerName": "B", "result": {"type": "HOME"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}},
                    ],
                }
            },
        }
    }
    assert parse_competition_page(raw) == []


def test_skips_runner_with_inactive_status():
    raw = {
        "attachments": {
            "events": {"1": {"eventId": 1, "name": "A @ B", "openDate": "2026-01-01T00:00:00.000Z"}},
            "markets": {
                "927.1": {
                    "marketId": "927.1", "eventId": 1, "competitionId": 1,
                    "marketType": "MONEY_LINE", "marketStatus": "OPEN",
                    "numberOfRunners": 2,
                    "runners": [
                        {"selectionId": 1, "runnerName": "A", "result": {"type": "AWAY"},
                         "runnerStatus": "SUSPENDED",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 2.0}}}},
                        {"selectionId": 2, "runnerName": "B", "result": {"type": "HOME"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}},
                    ],
                }
            },
        }
    }
    assert parse_competition_page(raw) == []
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_parsing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paddypower_scraper.models'` (or `.parsing`), since neither file exists yet.

- [ ] **Step 5: Implement `models.py`**

`src/paddypower_scraper/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamPrice:
    team_name: str
    selection_id: int
    decimal_odds: float
    home_or_away: str  # "HOME" | "AWAY"


@dataclass(frozen=True)
class NFLGameOdds:
    """One NFL moneyline market: both teams' current decimal odds."""
    market_id: str
    event_id: str
    event_name: str          # e.g. "Chicago Bears @ Detroit Lions" ("Away @ Home")
    kickoff_time: str        # ISO 8601 UTC, from the event's openDate
    competition_id: int
    teams: tuple[TeamPrice, TeamPrice]
```

- [ ] **Step 6: Implement `parsing.py`**

`src/paddypower_scraper/parsing.py`:

```python
from __future__ import annotations

from .models import NFLGameOdds, TeamPrice


def parse_competition_page(raw: dict) -> list[NFLGameOdds]:
    """Every open NFL moneyline market on this competition page, with both
    teams' current decimal odds."""
    attachments = raw.get("attachments", {})
    events = attachments.get("events", {})
    markets = attachments.get("markets", {})
    out: list[NFLGameOdds] = []
    for market in markets.values():
        game = _parse_market(market, events)
        if game is not None:
            out.append(game)
    return out


def _parse_market(market: dict, events: dict) -> NFLGameOdds | None:
    try:
        if market.get("marketType") != "MONEY_LINE":
            return None
        if market.get("marketStatus") != "OPEN":
            return None
        if market.get("numberOfRunners") != 2:
            return None
        event = events.get(str(market["eventId"]))
        if event is None:
            return None
        runners = market["runners"]
        if len(runners) != 2:
            return None
        team_a = _parse_runner(runners[0])
        team_b = _parse_runner(runners[1])
        if team_a is None or team_b is None:
            return None
        return NFLGameOdds(
            market_id=market["marketId"],
            event_id=str(market["eventId"]),
            event_name=event["name"],
            kickoff_time=event["openDate"],
            competition_id=market["competitionId"],
            teams=(team_a, team_b),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_runner(runner: dict) -> TeamPrice | None:
    try:
        if runner.get("runnerStatus") != "ACTIVE":
            return None
        decimal_odds = runner["winRunnerOdds"]["trueOdds"]["decimalOdds"]["decimalOdds"]
        return TeamPrice(
            team_name=runner["runnerName"],
            selection_id=runner["selectionId"],
            decimal_odds=float(decimal_odds),
            home_or_away=runner["result"]["type"],
        )
    except (KeyError, TypeError, ValueError):
        return None
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_parsing.py -v`
Expected: PASS — all 7 tests green.

- [ ] **Step 8: Commit**

```bash
git add src/paddypower_scraper/__init__.py src/paddypower_scraper/models.py src/paddypower_scraper/parsing.py tests/conftest.py tests/fixtures/paddypower_competition_page_sample.json tests/test_parsing.py
git commit -m "Add paddypower_scraper domain models and competition-page parsing"
```

---

### Task 2: API URL builder + Cloudflare-gated browser session

**Files:**
- Create: `src/paddypower_scraper/api.py`
- Create: `src/paddypower_scraper/browser.py`
- Test: `tests/test_api.py`
- Modify: `pyproject.toml` (add `playwright` dependency)

**Interfaces:**
- Produces (used by Task 3):
  - `api.NFL_PRESEASON_COMPETITION_ID: int = 11432305`, `api.NFL_COMPETITION_ID: int = 12282733`
  - `api.competition_page_url(competition_id: int) -> str`
  - `browser.BrowserSession` — context manager; `.fetch_json(url: str, timeout_ms: int = 20_000) -> dict`; raises `browser.BrowserFetchError` on failure

- [ ] **Step 1: Add the `playwright` dependency**

In `pyproject.toml`, add `"playwright>=1.42"` to the `dependencies` list (alongside the existing `httpx>=0.27`).

Run: `uv sync`
Expected: installs `playwright`, no errors.

Run: `uv run playwright install chromium`
Expected: downloads headless Chromium (~150MB), no errors. This is a one-time setup step (matching `horsey-scraper`'s README) — note it for the reader but it isn't something a test asserts.

- [ ] **Step 2: Write the failing test for the URL builder**

`tests/test_api.py`:

```python
from __future__ import annotations

from paddypower_scraper.api import (
    NFL_COMPETITION_ID,
    NFL_PRESEASON_COMPETITION_ID,
    competition_page_url,
)


def test_nfl_preseason_competition_id_is_correct():
    assert NFL_PRESEASON_COMPETITION_ID == 11432305


def test_nfl_regular_season_competition_id_is_correct():
    assert NFL_COMPETITION_ID == 12282733


def test_competition_page_url_includes_the_competition_id():
    url = competition_page_url(11432305)
    assert url.startswith("https://apisms.paddypower.com/smspp/competition-page/v3?")
    assert "competitionId=11432305" in url
    assert "eventTypeId=6423" in url


def test_competition_page_url_differs_by_competition_id():
    assert competition_page_url(1) != competition_page_url(2)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paddypower_scraper.api'`.

- [ ] **Step 4: Implement `api.py`**

`src/paddypower_scraper/api.py`:

```python
"""PaddyPower NFL endpoint constants and URL builder. No I/O."""

from __future__ import annotations

APP_KEY = "vsd0Rm5ph2sS2uaK"
AMERICAN_FOOTBALL_EVENT_TYPE_ID = 6423

# Two distinct competitions on PaddyPower's side — querying only the
# regular-season one would silently miss every preseason game.
NFL_PRESEASON_COMPETITION_ID = 11432305
NFL_COMPETITION_ID = 12282733

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
LOCALE = "en-GB"
TIMEZONE = "Europe/Dublin"

WARMUP_URL = "https://www.paddypower.com/american-football"

_COMPETITION_PAGE_BASE = (
    "https://apisms.paddypower.com/smspp/competition-page/v3"
    f"?_ak={APP_KEY}&betexRegion=IRL&capiJurisdiction=intl"
    "&countryCode=IE&currencyCode=EUR"
    f"&eventTypeId={AMERICAN_FOOTBALL_EVENT_TYPE_ID}&exchangeLocale=en_GB"
    "&includeBadges=true&includeLayout=true&includePrices=true"
    "&includeSeoCards=true&includeSeoFooter=true&language=en"
    "&loggedIn=false&regionCode=IRE"
)


def competition_page_url(competition_id: int) -> str:
    """Build a competition-page/v3 URL for the given NFL competition id."""
    return f"{_COMPETITION_PAGE_BASE}&competitionId={competition_id}"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 6: Implement `browser.py`**

`src/paddypower_scraper/browser.py` — copied from `horsey-scraper`'s `src/paddypower_scraper/browser.py` (same proven Cloudflare-warmup pattern), adapted to import from this module's `api.py`:

```python
"""Playwright-driven browser session for Cloudflare-gated PaddyPower calls.

One BrowserSession per scraper run. Warms up once on __enter__ to earn
the cf_clearance cookie, then reuses the same browser context for every
fetch_json call."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Type

from playwright.sync_api import Playwright, sync_playwright

from .api import LOCALE, TIMEZONE, USER_AGENT, WARMUP_URL


class BrowserFetchError(Exception):
    """Raised when an in-page fetch returns non-2xx, fails to evaluate,
    or returns invalid JSON."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


_FETCH_JS = """
async ([url, timeoutMs]) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const r = await fetch(url, {
            method: 'GET',
            credentials: 'include',
            headers: { 'accept': 'application/json, text/plain, */*' },
            signal: controller.signal,
        });
        if (!r.ok) {
            const text = await r.text();
            throw new Error('HTTP ' + r.status + ': ' + text.slice(0, 500));
        }
        return await r.text();
    } finally {
        clearTimeout(timer);
    }
}
"""


class BrowserSession:
    """Context manager. Launches headless Chromium and warms it up on
    __enter__; closes everything on __exit__."""

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            locale=LOCALE,
            timezone_id=TIMEZONE,
        )
        self._page = self._context.new_page()
        self._page.goto(WARMUP_URL, timeout=20_000)
        self._page.wait_for_load_state("domcontentloaded", timeout=15_000)
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._pw is not None:
                self._pw.stop()

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        """Run an in-page fetch() against `url` and return the parsed JSON.

        Raises BrowserFetchError on HTTP non-2xx, evaluation failure, or
        invalid JSON."""
        if self._page is None:
            raise RuntimeError("BrowserSession not entered")
        try:
            body = self._page.evaluate(_FETCH_JS, [url, timeout_ms])
        except Exception as e:
            raise BrowserFetchError(url, str(e)) from e
        if not isinstance(body, str):
            raise BrowserFetchError(url, f"unexpected response type: {type(body).__name__}")
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise BrowserFetchError(url, f"invalid JSON: {e}") from e
```

There is no unit test for `browser.py` itself in this task — it requires a real
browser and is exercised live in Task 3's integration test and live-run
verification, matching how `horsey-scraper` tests its equivalent module.

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests from Task 1 and Task 2 green (no regressions).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/paddypower_scraper/api.py src/paddypower_scraper/browser.py tests/test_api.py
git commit -m "Add paddypower_scraper API URL builder and Cloudflare-gated browser session"
```

---

### Task 3: Scraper orchestration + runnable entry point

**Files:**
- Create: `src/paddypower_scraper/scraper.py`
- Create: `src/paddypower_scraper/__main__.py`
- Test: `tests/test_scraper.py`
- Test: `tests/test_scraper_integration.py`

**Interfaces:**
- Consumes: `api.NFL_PRESEASON_COMPETITION_ID`, `api.NFL_COMPETITION_ID`, `api.competition_page_url` (Task 2); `browser.BrowserSession`, `browser.BrowserFetchError` (Task 2); `models.NFLGameOdds` (Task 1); `parsing.parse_competition_page` (Task 1)
- Produces: `scraper.DEFAULT_COMPETITION_IDS: tuple[int, ...]`, `scraper.scrape_nfl_moneylines(session, competition_ids: tuple[int, ...] = DEFAULT_COMPETITION_IDS) -> list[NFLGameOdds]`

- [ ] **Step 1: Write the failing tests for `scrape_nfl_moneylines`**

`tests/test_scraper.py`:

```python
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


def test_default_competition_ids_are_preseason_and_regular_season():
    from paddypower_scraper.scraper import DEFAULT_COMPETITION_IDS
    assert DEFAULT_COMPETITION_IDS == (11432305, 12282733)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paddypower_scraper.scraper'`.

- [ ] **Step 3: Implement `scraper.py`**

`src/paddypower_scraper/scraper.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: PASS — all 3 tests green.

- [ ] **Step 5: Add the runnable entry point**

`src/paddypower_scraper/__main__.py`:

```python
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .browser import BrowserSession
from .scraper import scrape_nfl_moneylines

OUTPUT_PATH = Path("paddypower_nfl.json")


def main() -> int:
    with BrowserSession() as session:
        games = scrape_nfl_moneylines(session)
    output = {
        "game_count": len(games),
        "games": [_game_to_dict(g) for g in games],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"Wrote {OUTPUT_PATH} ({len(games)} games)")
    return 0


def _game_to_dict(game) -> dict:
    d = dataclasses.asdict(game)
    d["teams"] = list(d["teams"])
    return d


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Add an opt-in live integration test**

`tests/test_scraper_integration.py`:

```python
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
```

Run: `RUN_INTEGRATION=1 uv run pytest tests/test_scraper_integration.py -v -m integration`
Expected: PASS against the live API (NFL preseason games are open right now).

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests green; the two `integration`-marked tests skip by default.

- [ ] **Step 8: Verify it actually runs against the live Paddy Power API**

Run: `uv run python -m paddypower_scraper`
Expected: Cloudflare warmup + fetch of both competitions (~10-20s, real browser launch), then `Wrote paddypower_nfl.json (N games)` with `N >= 1` (both preseason and regular-season NFL games are currently listed). Inspect the written `paddypower_nfl.json` to confirm it contains real team names, decimal odds, and kickoff times — no tracebacks.

Do not commit `paddypower_nfl.json` — add `paddypower_nfl.json` to `.gitignore` if it isn't already covered (check the existing `.gitignore` first; it may already have a pattern that covers this, otherwise add a specific line for it).

- [ ] **Step 9: Commit**

```bash
git add src/paddypower_scraper/scraper.py src/paddypower_scraper/__main__.py tests/test_scraper.py tests/test_scraper_integration.py .gitignore
git commit -m "Add paddypower_scraper orchestration and a runnable entry point"
```

---

## Self-Review Notes

- **Spec coverage:** Paddy Power NFL odds fetching (both preseason and regular-season competitions), decimal-odds output ready for the value-bet formula, non-fatal per-competition error handling, no credentials needed — all match the spec's `paddypower_scraper` module description and Non-goals. Team/game matching against Polymarket, bet365, the edge calculator, and email notification remain out of scope for this plan, per the spec's subsystem list.
- **Placeholder scan:** no TBDs; every step has complete, runnable code, built against real captured API payloads (not fabricated field names).
- **Type consistency:** `NFLGameOdds` and `TeamPrice` field names are identical across `models.py`, `parsing.py`, `scraper.py`'s tests, and `__main__.py`. `scrape_nfl_moneylines`'s signature (`session`, `competition_ids`) matches between Task 3's implementation and its tests. `BrowserSession.fetch_json`'s signature matches between Task 2's implementation and Task 3's `scraper.py` usage.
- **Credential hygiene:** confirmed no cookie, `cf_clearance`, or session-token value from this plan's live-API research appears anywhere in this document's code blocks or fixture data — only market/event/odds data, which is public.
