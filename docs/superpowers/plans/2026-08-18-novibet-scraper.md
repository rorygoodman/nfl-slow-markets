# Novibet NFL Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `novibet_scraper` module — fetches Novibet's current NFL moneyline (match-winner) odds for both the preseason and regular-season market-view groups, replacing bet365 as this project's second bookmaker (per the spec's updated scope).

**Architecture:** A pure `parsing.py` turns Novibet's `location/v2` feed JSON (verified live against the real API) into `NFLGameOdds` objects — fully unit-testable against a real captured fixture, no I/O. A `BrowserSession` (Playwright headless Chromium, copied from `horsey-scraper`'s proven `novibet_scraper.browser` pattern — Cloudflare warmup + `x-gw-*` gateway headers on every in-page `fetch()`) does the actual network calls; a bare `curl` replay was verified live to get Cloudflare-blocked (403 "Attention Required"), same as `paddypower_scraper`. `scraper.py` fetches both market-view groups (preseason + regular season), with **two layers of non-fatal handling per group from the start** (a fetch-failure guard and a separate parse-failure guard, plus a total-failure signal when every group fails) — this project's two prior scraper modules both needed a review round to discover these gaps after the fact; this plan bakes them in from day one instead.

**Tech Stack:** Python ≥3.11, `uv`, `playwright` (already a dependency from `paddypower_scraper`), `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-17-nfl-slow-markets-design.md`

## Global Constraints

- Python ≥3.11, managed with `uv`.
- Decimal odds only — Novibet's feed's `price` field is already decimal (confirmed live: `1.78`, `2.0`, etc., driven by the `oddsR=2` query param), matching the spec's `value_bet_edge(decimal_odds, true_prob)` formula directly. The feed also carries a separate `oddsText` field with fractional-format strings ("3/4", "1/1") — never use it; use `price` only.
- `betTypeSysname == "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW"` is the reliable machine-readable filter for "this is the moneyline market" — do not filter on any caption/display text field.
- **Never hardcode, log, or commit any session cookie, `cf_clearance` value, or other credential.** This plan's research used cookies pasted directly by the user from their own browser session for API-discovery purposes only — none of that data appears anywhere in this plan's code or fixtures.
- **Every scraper call site must have independent, non-fatal handling for BOTH the fetch step and the parse step** (not just fetch) — a malformed-but-successfully-fetched response for one market-view group must never crash the whole scrape or silently discard a different group's already-collected results. This was a real, confirmed bug found in `paddypower_scraper`'s task-level review; build it in from the start here instead of waiting to rediscover it.
- **The scraper must signal when every configured market-view group failed** (fetch or parse), distinct from a legitimate zero-games result (e.g. off-season) — raise a dedicated exception rather than silently writing an empty, "successful" output file. This was a real, confirmed bug found in `paddypower_scraper`'s final whole-branch review; build it in from the start here instead.
- Non-fatal per-record parsing: a single malformed game/market/bet-item inside an otherwise-valid response must not discard the rest of that response — catch `(AttributeError, KeyError, TypeError, ValueError)` at the per-item level (all four, not just three — `paddypower_scraper`'s final review found a real gap where `AttributeError` was missing from a similar exception tuple, silently turning "skip one bad record" into "discard 30+ good records").
- No credentials file needed — Novibet's odds pages are public, unauthenticated (matching how `horsey-scraper` already scrapes Novibet's horse-racing feed).
- Read-only: only HTTP GET requests (via in-page `fetch()`), no order/bet placement anywhere in this module.
- This plan covers `novibet_scraper` only. Team/game matching against Polymarket and Paddy Power, the arb calculation, and the orchestrator remain out of scope, covered by future plans.

---

## Verified live API details (checked against the real Novibet API on 2026-08-18)

- **Endpoint:** `GET https://www.novibet.ie/spt/feed/marketviews/location/v2/{location_id}/{market_view_group_id}/?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE&timestamp={cache_buster}`. `location_id` is the fixed literal `"4324"` — its exact meaning is unclear (the same literal value appears in `horsey-scraper`'s horse-racing feed URL in the same position, labeled `_SPORT_ID` there, but it also works unchanged for American Football here, so it is likely not sport-specific despite that name) — treat it as an opaque required constant, verified working, not something to second-guess.
- **Two distinct market-view-group IDs are needed, not one** (same lesson as `paddypower_scraper`'s two competition IDs):
  - `5813718` — NFL Preseason (confirmed live: contains HOU Texans @ LV Raiders, LA Chargers @ SF 49ers, PIT Steelers @ NY Jets, and more Aug 21+ 2026 games — matches the live Polymarket/Paddy Power preseason games found while building earlier modules).
  - `4799943` — NFL regular season (confirmed live via the same page's non-preseason tab).
  - A curl replay of either request without a live browser gets Cloudflare-blocked (403 "Attention Required! | Cloudflare") — confirmed live during this plan's research, matching `paddypower_scraper`'s exact finding. `BrowserSession` (Task 2) is required.
- **Response shape:** a top-level JSON **array** (not an object) of "location" objects: `[{marketViewId, marketViewGroupId, rootMarketViewGroupId, betViews: [{marketCaptions: [...], items: [...]}]}]`.
  - Each `item` (one game): `{eventBetContextId, additionalCaptions: {competitor1, competitor2}, startDate (ISO 8601 with UTC offset), path, markets: [...]}`.
  - Each `market`: `{marketId, betTypeSysname, betItems: [...]}`. For the moneyline market (`betTypeSysname == "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW"`), `betItems` has exactly 2 entries: `{id, code ("1" or "2"), price (decimal float), oddsText (fractional string, unused), isAvailable (bool)}`. `code == "1"` maps to `additionalCaptions.competitor1`; `code == "2"` maps to `competitor2` — confirmed by directly cross-referencing a real captured example (HOU Texans @ LV Raiders: code "1" → price 1.78 → Texans is `competitor1`; code "2" → price 2.0 → Raiders is `competitor2`).
- **`WARMUP_URL`:** `https://www.novibet.ie/sports/american-football/4372609/nfl/nfl/4374408` — a real URL observed directly as the `referer` header of the user's own live browser request, not a guess. Matches `horsey-scraper`'s established pattern: visiting any real page on the site earns the Cloudflare clearance cookie needed for subsequent same-origin `fetch()` calls.

---

### Task 1: Domain models + pure parsing logic (TDD, fixture-based)

**Files:**
- Create: `src/novibet_scraper/__init__.py`
- Create: `src/novibet_scraper/models.py`
- Create: `src/novibet_scraper/parsing.py`
- Modify: `pyproject.toml` (add `"src/novibet_scraper"` to the wheel `packages` list)
- Create: `tests/fixtures/novibet_location_feed_sample.json`
- Test: `tests/test_novibet_parsing.py`

**Interfaces:**
- Produces (used by Task 3):
  - `models.TeamPrice(team_name: str, selection_id: str, decimal_odds: float)`
  - `models.NFLGameOdds(market_id: int, event_id: str, event_name: str, kickoff_time: str, market_view_group_id: int, teams: tuple[TeamPrice, TeamPrice])`
  - `parsing.parse_location_feed(raw, market_view_group_id: int) -> list[NFLGameOdds]`

- [ ] **Step 1: Create the fixture file**

`tests/fixtures/novibet_location_feed_sample.json` — a real, captured `location/v2` payload shape trimmed to two games: one valid moneyline market plus an extra non-moneyline market (to test the `betTypeSysname` filter), and one game whose moneyline market has an unavailable side (to test the `isAvailable` filter):

```json
[
  {
    "marketViewId": 6956808,
    "marketViewGroupId": 5813718,
    "rootMarketViewGroupId": 4372609,
    "path": "preseason",
    "betViews": [
      {
        "items": [
          {
            "eventBetContextId": 47678025,
            "additionalCaptions": {
              "competitor1": "HOU Texans",
              "competitor2": "LV Raiders"
            },
            "startDate": "2026-08-21T00:00:00+00:00",
            "path": "preseason/hou-texans-lv-raiders",
            "markets": [
              {
                "marketId": 1709836937,
                "betTypeSysname": "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW",
                "betItems": [
                  {"id": "7127413176", "code": "1", "price": 1.78, "oddsText": "3/4", "isAvailable": true},
                  {"id": "7127413177", "code": "2", "price": 2.0, "oddsText": "1/1", "isAvailable": true}
                ]
              },
              {
                "marketId": 1710057840,
                "betTypeSysname": "AMERICAN_FOOTBALL_UNDER_OVER",
                "betItems": [
                  {"id": "7128401868", "code": "O", "price": 1.83, "oddsText": "5/6", "isAvailable": true},
                  {"id": "7128401869", "code": "U", "price": 1.82, "oddsText": "4/5", "isAvailable": true}
                ]
              }
            ]
          },
          {
            "eventBetContextId": 47678099,
            "additionalCaptions": {
              "competitor1": "PIT Steelers",
              "competitor2": "NY Jets"
            },
            "startDate": "2026-08-21T23:00:00+00:00",
            "path": "preseason/pit-steelers-ny-jets",
            "markets": [
              {
                "marketId": 1709836999,
                "betTypeSysname": "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW",
                "betItems": [
                  {"id": "7127413200", "code": "1", "price": 1.55, "oddsText": "8/15", "isAvailable": true},
                  {"id": "7127413201", "code": "2", "price": 2.4, "oddsText": "7/5", "isAvailable": false}
                ]
              }
            ]
          }
        ]
      }
    ]
  }
]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_novibet_parsing.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_novibet_parsing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper.models'` (or `.parsing`).

- [ ] **Step 4: Add `"src/novibet_scraper"` to `pyproject.toml`'s wheel packages list**, alongside the existing `"src/polymarket_monitor"`, `"src/paddypower_scraper"`, `"src/common"`, and `"src/notifier"` entries.

- [ ] **Step 5: Implement `models.py`**

`src/novibet_scraper/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamPrice:
    team_name: str
    selection_id: str
    decimal_odds: float


@dataclass(frozen=True)
class NFLGameOdds:
    """One NFL moneyline market: both teams' current decimal odds."""
    market_id: int
    event_id: str
    event_name: str          # e.g. "HOU Texans vs LV Raiders"
    kickoff_time: str        # ISO 8601 with UTC offset, from the item's startDate
    market_view_group_id: int
    teams: tuple[TeamPrice, TeamPrice]
```

- [ ] **Step 6: Implement `parsing.py`**

`src/novibet_scraper/parsing.py`:

```python
from __future__ import annotations

from .models import NFLGameOdds, TeamPrice

_MONEYLINE_BET_TYPE = "AMERICAN_FOOTBALL_MATCH_RESULT_NO_DRAW"


def parse_location_feed(raw, market_view_group_id: int) -> list[NFLGameOdds]:
    """Every fully-available NFL moneyline market in this location feed
    response, with both teams' current decimal odds."""
    if not isinstance(raw, list):
        return []
    out: list[NFLGameOdds] = []
    for location in raw:
        if not isinstance(location, dict):
            continue
        for bet_view in location.get("betViews") or []:
            if not isinstance(bet_view, dict):
                continue
            for item in bet_view.get("items") or []:
                game = _parse_item(item, market_view_group_id)
                if game is not None:
                    out.append(game)
    return out


def _parse_item(item, market_view_group_id: int) -> NFLGameOdds | None:
    try:
        captions = item["additionalCaptions"]
        competitor1 = captions["competitor1"]
        competitor2 = captions["competitor2"]
        if not isinstance(competitor1, str) or not competitor1:
            return None
        if not isinstance(competitor2, str) or not competitor2:
            return None
        event_id = str(item["eventBetContextId"])
        kickoff_time = item["startDate"]

        market = _find_moneyline_market(item.get("markets"))
        if market is None:
            return None

        team1 = _parse_bet_item(market["betItems"], "1", competitor1)
        team2 = _parse_bet_item(market["betItems"], "2", competitor2)
        if team1 is None or team2 is None:
            return None

        return NFLGameOdds(
            market_id=market["marketId"],
            event_id=event_id,
            event_name=f"{competitor1} vs {competitor2}",
            kickoff_time=kickoff_time,
            market_view_group_id=market_view_group_id,
            teams=(team1, team2),
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _find_moneyline_market(markets):
    if not isinstance(markets, list):
        return None
    for market in markets:
        if not isinstance(market, dict):
            continue
        if market.get("betTypeSysname") != _MONEYLINE_BET_TYPE:
            continue
        bet_items = market.get("betItems")
        if isinstance(bet_items, list) and len(bet_items) == 2:
            return market
    return None


def _parse_bet_item(bet_items, code: str, team_name: str) -> TeamPrice | None:
    for bet_item in bet_items:
        if not isinstance(bet_item, dict):
            continue
        if bet_item.get("code") != code:
            continue
        if not bet_item.get("isAvailable"):
            return None
        price = bet_item.get("price")
        bet_item_id = bet_item.get("id")
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            return None
        if not isinstance(bet_item_id, str) or not bet_item_id:
            return None
        return TeamPrice(team_name=team_name, selection_id=bet_item_id, decimal_odds=float(price))
    return None
```

(`isinstance(price, bool)` is checked separately because `bool` is a subclass of `int` in Python — without this, a stray `True`/`False` value in the `price` field would otherwise pass the `isinstance(price, (int, float))` check.)

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_novibet_parsing.py -v`
Expected: PASS — all 7 tests green.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/novibet_scraper/__init__.py src/novibet_scraper/models.py src/novibet_scraper/parsing.py tests/fixtures/novibet_location_feed_sample.json tests/test_novibet_parsing.py
git commit -m "Add novibet_scraper domain models and location-feed parsing"
```

---

### Task 2: API URL builder + Cloudflare-gated browser session

**Files:**
- Create: `src/novibet_scraper/api.py`
- Create: `src/novibet_scraper/browser.py`
- Test: `tests/test_novibet_api.py`

**Interfaces:**
- Produces (used by Task 3):
  - `api.NFL_PRESEASON_MARKET_VIEW_GROUP_ID: int = 5813718`, `api.NFL_MARKET_VIEW_GROUP_ID: int = 4799943`
  - `api.location_feed_url(market_view_group_id: int, timestamp_ms: int | None = None) -> str`
  - `browser.BrowserSession` — context manager; `.fetch_json(url: str, timeout_ms: int = 20_000) -> dict | list`; raises `browser.BrowserFetchError` on failure

- [ ] **Step 1: Write the failing tests for the URL builder**

`tests/test_novibet_api.py`:

```python
from __future__ import annotations

from novibet_scraper.api import (
    NFL_MARKET_VIEW_GROUP_ID,
    NFL_PRESEASON_MARKET_VIEW_GROUP_ID,
    location_feed_url,
)


def test_nfl_preseason_market_view_group_id_is_correct():
    assert NFL_PRESEASON_MARKET_VIEW_GROUP_ID == 5813718


def test_nfl_regular_season_market_view_group_id_is_correct():
    assert NFL_MARKET_VIEW_GROUP_ID == 4799943


def test_location_feed_url_includes_the_group_id_and_fixed_params():
    url = location_feed_url(5813718, timestamp_ms=1234567890)
    assert url == (
        "https://www.novibet.ie/spt/feed/marketviews/location/v2/4324/5813718/"
        "?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE&timestamp=1234567890"
    )


def test_location_feed_url_differs_by_group_id():
    a = location_feed_url(5813718, timestamp_ms=1)
    b = location_feed_url(4799943, timestamp_ms=1)
    assert a != b


def test_location_feed_url_generates_a_timestamp_when_not_given():
    url = location_feed_url(5813718)
    assert "timestamp=" in url
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_novibet_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper.api'`.

- [ ] **Step 3: Implement `api.py`**

`src/novibet_scraper/api.py`:

```python
"""Novibet NFL endpoint constants and URL builder. No I/O."""

from __future__ import annotations

import time

# Fixed literal required by this endpoint family — meaning unclear (the
# same value appears in horsey-scraper's horse-racing feed URL in the same
# position, but it works unchanged for American Football here too), so
# treat it as an opaque required constant, not a per-sport id.
_LOCATION_ID = "4324"

NFL_PRESEASON_MARKET_VIEW_GROUP_ID = 5813718
NFL_MARKET_VIEW_GROUP_ID = 4799943

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
LOCALE = "en-IE"
TIMEZONE = "Europe/Dublin"

WARMUP_URL = "https://www.novibet.ie/sports/american-football/4372609/nfl/nfl/4374408"

API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "x-gw-domain-key": "_IE",
    "x-gw-cms-key": "_IE",
    "x-gw-application-name": "NoviIE",
    "x-gw-currency-sysname": "EUR",
    "x-gw-country-sysname": "IE",
    "x-gw-language-sysname": "en-IE",
    "x-gw-client-timezone": "Europe/Dublin",
    "x-gw-channel": "WebPC",
    "x-gw-client-layout": "Desktop",
    "x-gw-odds-representation": "Fractional",
}

_LOCATION_FEED_BASE = "https://www.novibet.ie/spt/feed/marketviews/location/v2"


def location_feed_url(market_view_group_id: int, timestamp_ms: "int | None" = None) -> str:
    """Build a location/v2 feed URL for the given NFL market-view group id."""
    ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    return (
        f"{_LOCATION_FEED_BASE}/{_LOCATION_ID}/{market_view_group_id}/"
        f"?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE&timestamp={ts}"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_novibet_api.py -v`
Expected: PASS — all 5 tests green.

- [ ] **Step 5: Implement `browser.py`**

`src/novibet_scraper/browser.py` — copied from `horsey-scraper`'s `src/novibet_scraper/browser.py` (same proven Cloudflare-warmup-plus-gateway-headers pattern), adapted to import from this module's `api.py`:

```python
"""Playwright-driven browser session for Cloudflare-gated Novibet calls.

One BrowserSession per scraper run. Warms up once on __enter__ to earn
the Cloudflare clearance cookie, then reuses the same browser context for
every fetch_json call. The x-gw-* gateway headers ride on each in-page
fetch."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Type

from playwright.sync_api import Playwright, sync_playwright

from .api import API_HEADERS, LOCALE, TIMEZONE, USER_AGENT, WARMUP_URL


class BrowserFetchError(Exception):
    """Raised when an in-page fetch returns non-2xx, fails to evaluate,
    or returns invalid JSON."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


_FETCH_JS = """
async ([url, headers, timeoutMs]) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const r = await fetch(url, {
            method: 'GET',
            credentials: 'include',
            headers: headers,
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
        self._page.goto(WARMUP_URL, timeout=30_000)
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

    def fetch_json(self, url: str, timeout_ms: int = 20_000):
        """Run an in-page fetch() against `url` (with the gateway headers)
        and return the parsed JSON.

        Raises BrowserFetchError on HTTP non-2xx, evaluation failure, or
        invalid JSON."""
        if self._page is None:
            raise RuntimeError("BrowserSession not entered")
        try:
            body = self._page.evaluate(_FETCH_JS, [url, API_HEADERS, timeout_ms])
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
verification, matching how `paddypower_scraper` tests its equivalent module.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests from Task 1 and Task 2 green (no regressions).

- [ ] **Step 7: Commit**

```bash
git add src/novibet_scraper/api.py src/novibet_scraper/browser.py tests/test_novibet_api.py
git commit -m "Add novibet_scraper API URL builder and Cloudflare-gated browser session"
```

---

### Task 3: Scraper orchestration + runnable entry point

**Files:**
- Create: `src/novibet_scraper/scraper.py`
- Create: `src/novibet_scraper/__main__.py`
- Test: `tests/test_novibet_scraper.py`
- Test: `tests/test_novibet_scraper_integration.py`

**Interfaces:**
- Consumes: `api.NFL_PRESEASON_MARKET_VIEW_GROUP_ID`, `api.NFL_MARKET_VIEW_GROUP_ID`, `api.location_feed_url` (Task 2); `browser.BrowserSession`, `browser.BrowserFetchError` (Task 2); `models.NFLGameOdds` (Task 1); `parsing.parse_location_feed` (Task 1)
- Produces: `scraper.DEFAULT_MARKET_VIEW_GROUP_IDS: tuple[int, ...]`, `scraper.AllMarketViewGroupsFailedError`, `scraper.scrape_nfl_moneylines(session, market_view_group_ids: tuple[int, ...] = DEFAULT_MARKET_VIEW_GROUP_IDS) -> list[NFLGameOdds]`

- [ ] **Step 1: Write the failing tests for `scrape_nfl_moneylines`**

`tests/test_novibet_scraper.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_novibet_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper.scraper'`.

- [ ] **Step 3: Implement `scraper.py`**

`src/novibet_scraper/scraper.py`:

```python
from __future__ import annotations

import sys

from .api import (
    NFL_MARKET_VIEW_GROUP_ID,
    NFL_PRESEASON_MARKET_VIEW_GROUP_ID,
    location_feed_url,
)
from .browser import BrowserFetchError
from .models import NFLGameOdds
from .parsing import parse_location_feed

DEFAULT_MARKET_VIEW_GROUP_IDS = (NFL_PRESEASON_MARKET_VIEW_GROUP_ID, NFL_MARKET_VIEW_GROUP_ID)


class AllMarketViewGroupsFailedError(Exception):
    """Raised when every configured market-view group failed (fetch or
    parse) — signals a total scrape failure, as opposed to a legitimate
    zero-games result (e.g. off-season)."""


def scrape_nfl_moneylines(
    session, market_view_group_ids: tuple[int, ...] = DEFAULT_MARKET_VIEW_GROUP_IDS
) -> list[NFLGameOdds]:
    """Fetch + parse every fully-available NFL moneyline market across the
    given market-view groups. A fetch failure or a parse failure for one
    group is logged to stderr and does not block the others. Raises
    AllMarketViewGroupsFailedError only if every configured group failed
    (fetch or parse) — a group that legitimately returns zero games is not
    a failure."""
    games: list[NFLGameOdds] = []
    succeeded = 0
    for group_id in market_view_group_ids:
        url = location_feed_url(group_id)
        try:
            raw = session.fetch_json(url)
        except BrowserFetchError as exc:
            print(f"novibet_scraper: market view group {group_id} fetch failed: {exc}",
                  file=sys.stderr)
            continue
        try:
            parsed = parse_location_feed(raw, group_id)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            print(f"novibet_scraper: market view group {group_id} parse failed: {exc}",
                  file=sys.stderr)
            continue
        games.extend(parsed)
        succeeded += 1

    if market_view_group_ids and succeeded == 0:
        raise AllMarketViewGroupsFailedError(
            f"all {len(market_view_group_ids)} configured market view group(s) failed"
        )
    return games
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_novibet_scraper.py -v`
Expected: PASS — all 7 tests green.

- [ ] **Step 5: Add the runnable entry point**

`src/novibet_scraper/__main__.py`:

```python
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from .browser import BrowserSession
from .scraper import AllMarketViewGroupsFailedError, scrape_nfl_moneylines

OUTPUT_PATH = Path("novibet_nfl.json")


def main() -> int:
    with BrowserSession() as session:
        try:
            games = scrape_nfl_moneylines(session)
        except AllMarketViewGroupsFailedError as exc:
            print(f"novibet_scraper: {exc}", file=sys.stderr)
            return 1

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

`tests/test_novibet_scraper_integration.py`:

```python
"""Opt-in live test against the real Novibet API (via a real headless
Chromium session — this is slow, ~10-20s, and needs network + the Chromium
browser installed via `uv run playwright install chromium`, already done
in this project).

Run with: RUN_INTEGRATION=1 uv run pytest -m integration
Skipped by default."""

from __future__ import annotations

import os

import pytest

from novibet_scraper.browser import BrowserSession
from novibet_scraper.scraper import scrape_nfl_moneylines

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

Run: `RUN_INTEGRATION=1 uv run pytest tests/test_novibet_scraper_integration.py -v -m integration`
Expected: PASS against the live API (NFL preseason games are open right now).

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests green; the `integration`-marked tests skip by default.

- [ ] **Step 8: Verify it actually runs against the live Novibet API**

Run: `uv run python -m novibet_scraper`
Expected: Cloudflare warmup + fetch of both market-view groups (~10-20s, real browser launch), then `Wrote novibet_nfl.json (N games)` with `N >= 1` (both preseason and regular-season NFL games are currently listed). Inspect the written `novibet_nfl.json` to confirm it contains real team names, decimal odds, and kickoff times — no tracebacks.

Add `novibet_nfl.json` to `.gitignore` if it isn't already covered by an existing pattern (check first — `paddypower_nfl.json` may already be covered by a pattern broad enough to include this, or may need its own line; either way don't commit this file).

- [ ] **Step 9: Commit**

```bash
git add src/novibet_scraper/scraper.py src/novibet_scraper/__main__.py tests/test_novibet_scraper.py tests/test_novibet_scraper_integration.py .gitignore
git commit -m "Add novibet_scraper orchestration and a runnable entry point"
```

---

## Self-Review Notes

- **Spec coverage:** Novibet NFL odds fetching (both preseason and regular-season market-view groups), decimal-odds output ready for the value-bet formula, non-fatal per-group error handling (fetch AND parse, plus total-failure signaling) — all match the spec's updated `novibet_scraper` module description and Non-goals. Team/game matching against Polymarket and Paddy Power, the edge calculator, and the orchestrator remain out of scope for this plan, per the spec's subsystem list.
- **Placeholder scan:** no TBDs; every step has complete, runnable code, built against real captured API payloads (not fabricated field names).
- **Type consistency:** `NFLGameOdds` and `TeamPrice` field names are identical across `models.py`, `parsing.py`, `scraper.py`'s tests, and `__main__.py`. `scrape_nfl_moneylines`'s signature (`session`, `market_view_group_ids`) matches between Task 3's implementation and its tests. `BrowserSession.fetch_json`'s signature matches between Task 2's implementation and Task 3's `scraper.py` usage. `AllMarketViewGroupsFailedError` is defined once in `scraper.py` and consumed identically by its own tests and `__main__.py`.
- **Credential hygiene:** confirmed no cookie, `cf_clearance`, or session-token value from this plan's live-API research appears anywhere in this document's code blocks or fixture data — only market/event/odds data, which is public.
- **Proactive lessons applied:** unlike `paddypower_scraper` (which needed a task-level review round to add the parse-failure guard, and a final-review round to add total-failure signaling and the `AttributeError` exception-tuple fix), this plan bakes all three directly into Task 1's `parsing.py` exception tuple and Task 3's `scraper.py` from the first draft.
