# Polymarket Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `polymarket_monitor` module — a standalone, runnable Python component that continuously polls Polymarket's live NFL game-winner markets and logs a detected move whenever a market's sell-side (best-ask) price changes by ≥5% relative to its price ~10 minutes earlier.

**Architecture:** A pure-logic `MoveDetector` (in-memory trailing-window state per market, no I/O) is fed by a thin Gamma-API `client` (one HTTP call per poll fetches every open NFL moneyline market's current best-ask in a single request — verified live against the real API, no per-token CLOB calls needed). A `poller` loop ties them together with error backoff, and `__main__` makes it directly runnable. This plan covers `polymarket_monitor` only — bookmaker scrapers, matching, arb math, and email notification are separate follow-up plans per the spec's subsystem decomposition.

**Tech Stack:** Python ≥3.11, `uv`, `httpx` for HTTP, `pytest` for tests — matching the tooling already used in the sibling `horsey-scraper` project.

**Spec:** `docs/superpowers/specs/2026-08-17-nfl-slow-markets-design.md`

## Global Constraints

- Python ≥3.11, managed with `uv` (mirrors `horsey-scraper`'s setup).
- Poll interval default: 30 seconds.
- Move threshold: **5% relative change** (5% of the prior price, e.g. 0.50 → 0.525), not percentage points.
- Trailing window: 10 minutes. A market needs ≥10 minutes of observation history before it can trigger; a reference sample that ages out of the window (via a polling gap) must not produce a false trigger.
- Reference price: the **sell side (best-ask)** of the market — this is the same reference used later for the value-bet edge calculation, per the approved spec.
- Read-only against Polymarket throughout: no wallet, no order placement, no position — this plan only ever issues HTTP GET requests.
- No persistence of price history across restarts — in-memory state only (accepted simplification, per spec Non-goals).
- Must never crash the poll loop: network/HTTP errors and malformed API data are caught and logged, not raised.

---

## Verified live API details (checked against the real Gamma/CLOB APIs on 2026-08-17)

- `GET https://gamma-api.polymarket.com/markets?tag_id=450&sports_market_types=moneyline&closed=false&limit=100` returns every open NFL moneyline market. `tag_id=450` is NFL's primary tag (confirmed via `GET https://gamma-api.polymarket.com/sports`, `sport: "nfl"` → `primaryTagId: 450`).
- Each market object includes (numeric, not string, for `bestAsk`/`bestBid`):
  ```json
  {
    "id": "2869647",
    "question": "Raiders vs. Texans",
    "outcomes": "[\"Raiders\", \"Texans\"]",
    "bestBid": 0.5,
    "bestAsk": 0.51,
    "gameStartTime": "2026-08-21 00:00:00+00",
    "closed": false
  }
  ```
  `outcomes` is a JSON-encoded string, not a native array — must be `json.loads`'d.
- `bestAsk` on the Gamma market object matches the live CLOB order book's true lowest ask exactly (cross-checked directly against `GET https://clob.polymarket.com/book?token_id=...` at the same moment) — so a single Gamma call per poll is sufficient; no per-token CLOB calls are needed for this module.
- The CLOB `/book` endpoint's documented "asks sorted ascending" does **not** hold in practice (observed descending in a live response) — this module avoids that endpoint entirely by using Gamma's `bestAsk` field directly, sidestepping the ambiguity.
- A 2-outcome market's `outcomes[0]` (e.g. "Raiders") is tracked as the market's representative price series — stable across polls since it's keyed by the same market `id` every time, and a move in one outcome implies a move in the complementary one, which is all this module needs to know (which team benefited is derived from the direction of the move).

---

### Task 1: Domain models + MoveDetector (pure logic, TDD)

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/polymarket_monitor/__init__.py`
- Create: `src/polymarket_monitor/models.py`
- Create: `src/polymarket_monitor/detector.py`
- Test: `tests/test_detector.py`

**Interfaces:**
- Produces (used by Task 2 and Task 3):
  - `models.MarketSnapshot(market_id: str, question: str, tracked_outcome: str, best_ask: float, game_start_time: str | None)`
  - `models.PriceSample(timestamp: datetime, price: float)`
  - `models.MoveEvent(market_id: str, question: str, tracked_outcome: str, old_price: float, new_price: float, relative_move: float, old_at: datetime, new_at: datetime)`
  - `detector.MoveDetector()` with `.observe(market_id: str, question: str, tracked_outcome: str, price: float, now: datetime) -> MoveEvent | None`

- [ ] **Step 1: Create the project scaffolding**

`pyproject.toml`:

```toml
[project]
name = "nfl-slow-markets"
version = "0.1.0"
description = "Polymarket-triggered NFL bookmaker value-bet alerting"
requires-python = ">=3.11"
dependencies = ["httpx>=0.27"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
polymarket-monitor = "polymarket_monitor.poller:run"

[tool.hatch.build.targets.wheel]
packages = ["src/polymarket_monitor"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = [
    "integration: live network test, opt-in via RUN_INTEGRATION=1",
]
```

`.gitignore`:

```
# Python
.venv/
.pytest_cache/
__pycache__/
**/__pycache__/
*.pyc

# IDE
.idea/
*.iml

# OS
.DS_Store

# Credentials — never commit. Real file lives at ~/.nfl-slow-markets/credentials.json.
credentials.json
*.env
```

Create empty `src/polymarket_monitor/__init__.py`.

- [ ] **Step 2: `uv sync` to create the environment**

Run: `uv sync`
Expected: creates `.venv/` and `uv.lock`, installs `httpx` and `pytest`, no errors.

- [ ] **Step 3: Write the failing tests for `MoveDetector`**

`tests/test_detector.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polymarket_monitor.detector import MoveDetector

T0 = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_no_trigger_without_ten_minutes_of_history():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    # A huge jump 5 minutes later, but we don't have 10 minutes of history yet.
    event = detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.90, T0 + timedelta(minutes=5))
    assert event is None


def test_triggers_at_exactly_five_percent_relative_move_up():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.525, T0 + timedelta(minutes=10)
    )
    assert event is not None
    assert event.old_price == 0.50
    assert event.new_price == 0.525
    assert round(event.relative_move, 6) == 0.05


def test_no_trigger_below_five_percent_relative_move():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.524, T0 + timedelta(minutes=10)
    )
    assert event is None


def test_triggers_on_downward_move():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.40, T0 + timedelta(minutes=10)
    )
    assert event is not None
    assert event.old_price == 0.50
    assert event.new_price == 0.40
    assert round(event.relative_move, 6) == 0.20


def test_reference_is_oldest_sample_still_inside_trailing_window():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.51, T0 + timedelta(minutes=3))
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.52, T0 + timedelta(minutes=6))
    # At T0+11min, the T0 sample (11 min old) has aged out of the 10-min
    # window; the reference should be the T0+3min sample (8 min old), not T0.
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.60, T0 + timedelta(minutes=11)
    )
    assert event is not None
    assert event.old_price == 0.51


def test_gap_exceeding_window_prunes_stale_reference_and_does_not_trigger():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    # Gap longer than the 10-minute window: the old sample ages out before
    # this poll arrives, so there's no valid "10 minutes ago" reference.
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.80, T0 + timedelta(minutes=25)
    )
    assert event is None


def test_markets_are_tracked_independently():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    detector.observe("m2", "49ers vs. Chargers", "49ers", 0.50, T0)
    event_m2 = detector.observe(
        "m2", "49ers vs. Chargers", "49ers", 0.80, T0 + timedelta(minutes=10)
    )
    event_m1 = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.50, T0 + timedelta(minutes=10)
    )
    assert event_m2 is not None
    assert event_m1 is None
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'polymarket_monitor.detector'` (or similar import error), since neither `models.py` nor `detector.py` exist yet.

- [ ] **Step 5: Implement `models.py`**

`src/polymarket_monitor/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketSnapshot:
    """One poll's reading of a single NFL moneyline market."""
    market_id: str
    question: str
    tracked_outcome: str
    best_ask: float
    game_start_time: str | None


@dataclass(frozen=True)
class PriceSample:
    timestamp: datetime
    price: float


@dataclass(frozen=True)
class MoveEvent:
    """A detected >=5% relative move in a market's tracked outcome price,
    measured against the oldest sample still inside the trailing window."""
    market_id: str
    question: str
    tracked_outcome: str
    old_price: float
    new_price: float
    relative_move: float
    old_at: datetime
    new_at: datetime
```

- [ ] **Step 6: Implement `detector.py`**

`src/polymarket_monitor/detector.py`:

```python
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import MoveEvent, PriceSample

DEFAULT_WINDOW = timedelta(minutes=10)
DEFAULT_THRESHOLD = 0.05


@dataclass
class _MarketState:
    first_seen_at: datetime
    samples: "deque[PriceSample]" = field(default_factory=deque)


class MoveDetector:
    """Tracks each market's trailing price window and flags a >=5%
    relative move (5% of the prior price), measured against the oldest
    sample still inside the trailing window. A market needs a full
    window of observation history before it can trigger."""

    def __init__(self, window: timedelta = DEFAULT_WINDOW, threshold: float = DEFAULT_THRESHOLD):
        self._window = window
        self._threshold = threshold
        self._states: dict[str, _MarketState] = {}

    def observe(
        self,
        market_id: str,
        question: str,
        tracked_outcome: str,
        price: float,
        now: datetime,
    ) -> MoveEvent | None:
        state = self._states.get(market_id)
        if state is None:
            state = _MarketState(first_seen_at=now)
            self._states[market_id] = state

        cutoff = now - self._window
        while state.samples and state.samples[0].timestamp < cutoff:
            state.samples.popleft()
        reference = state.samples[0] if state.samples else None

        state.samples.append(PriceSample(timestamp=now, price=price))

        if now - state.first_seen_at < self._window or reference is None:
            return None
        if reference.price <= 0:
            return None  # guards div-by-zero on malformed upstream data

        relative_move = abs(price - reference.price) / reference.price
        if relative_move < self._threshold:
            return None

        return MoveEvent(
            market_id=market_id,
            question=question,
            tracked_outcome=tracked_outcome,
            old_price=reference.price,
            new_price=price,
            relative_move=relative_move,
            old_at=reference.timestamp,
            new_at=now,
        )
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_detector.py -v`
Expected: PASS — all 7 tests green.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore uv.lock src/polymarket_monitor/__init__.py src/polymarket_monitor/models.py src/polymarket_monitor/detector.py tests/test_detector.py
git commit -m "Add MoveDetector: trailing-window relative-move detection"
```

---

### Task 2: Gamma API client

**Files:**
- Create: `src/polymarket_monitor/client.py`
- Test: `tests/test_client.py`
- Test: `tests/test_client_integration.py`

**Interfaces:**
- Consumes: `models.MarketSnapshot` (from Task 1)
- Produces (used by Task 3):
  - `client.fetch_nfl_moneyline_markets(client: httpx.Client | None = None) -> list[MarketSnapshot]`
  - `client.GAMMA_MARKETS_URL: str`, `client.NFL_TAG_ID: int` (constants, for reference/reuse by later scraper-matching tasks)

- [ ] **Step 1: Write the failing unit tests for market parsing**

`tests/test_client.py`:

```python
from __future__ import annotations

from polymarket_monitor.client import _parse_market
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'polymarket_monitor.client'`.

- [ ] **Step 3: Implement `client.py`**

`src/polymarket_monitor/client.py`:

```python
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
        snapshots = []
        for raw in response.json():
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS — all 7 tests green.

- [ ] **Step 5: Add an opt-in live integration test**

`tests/test_client_integration.py`:

```python
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
```

Run: `RUN_INTEGRATION=1 uv run pytest tests/test_client_integration.py -v -m integration`
Expected: PASS against the live API (NFL preseason games are open right now).

- [ ] **Step 6: Commit**

```bash
git add src/polymarket_monitor/client.py tests/test_client.py tests/test_client_integration.py
git commit -m "Add Gamma API client for open NFL moneyline markets"
```

---

### Task 3: Poller loop + runnable entry point

**Files:**
- Create: `src/polymarket_monitor/poller.py`
- Create: `src/polymarket_monitor/__main__.py`
- Test: `tests/test_poller.py`

**Interfaces:**
- Consumes: `client.fetch_nfl_moneyline_markets` (Task 2), `detector.MoveDetector` (Task 1)
- Produces: `poller.run(poll_interval: float = 30.0) -> None`, `poller.poll_once(client: httpx.Client, detector: MoveDetector) -> bool`

- [ ] **Step 1: Write the failing tests for `poll_once`**

`tests/test_poller.py`:

```python
from __future__ import annotations

import logging

import httpx

from polymarket_monitor import poller
from polymarket_monitor.detector import MoveDetector
from polymarket_monitor.models import MarketSnapshot, MoveEvent


class _RecordingDetector:
    def __init__(self):
        self.calls = []

    def observe(self, **kwargs):
        self.calls.append(kwargs)
        return None


class _AlwaysMovesDetector:
    def observe(self, **kwargs):
        return MoveEvent(
            market_id=kwargs["market_id"],
            question=kwargs["question"],
            tracked_outcome=kwargs["tracked_outcome"],
            old_price=0.50,
            new_price=0.60,
            relative_move=0.20,
            old_at=kwargs["now"],
            new_at=kwargs["now"],
        )


def test_poll_once_feeds_each_snapshot_to_the_detector(monkeypatch):
    snapshot = MarketSnapshot(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        best_ask=0.51, game_start_time="2026-08-21 00:00:00+00",
    )
    monkeypatch.setattr(poller, "fetch_nfl_moneyline_markets", lambda client: [snapshot])
    detector = _RecordingDetector()

    ok = poller.poll_once(client=object(), detector=detector)

    assert ok is True
    assert len(detector.calls) == 1
    call = detector.calls[0]
    assert call["market_id"] == "1"
    assert call["question"] == "Raiders vs. Texans"
    assert call["tracked_outcome"] == "Raiders"
    assert call["price"] == 0.51


def test_poll_once_logs_move_detected(monkeypatch, caplog):
    snapshot = MarketSnapshot(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        best_ask=0.60, game_start_time=None,
    )
    monkeypatch.setattr(poller, "fetch_nfl_moneyline_markets", lambda client: [snapshot])

    with caplog.at_level(logging.INFO):
        ok = poller.poll_once(client=object(), detector=_AlwaysMovesDetector())

    assert ok is True
    assert "MOVE DETECTED" in caplog.text
    assert "Raiders vs. Texans" in caplog.text


def test_poll_once_returns_false_and_logs_warning_on_fetch_error(monkeypatch, caplog):
    def _raise(client):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(poller, "fetch_nfl_moneyline_markets", _raise)

    with caplog.at_level(logging.WARNING):
        ok = poller.poll_once(client=object(), detector=MoveDetector())

    assert ok is False
    assert "Polymarket fetch failed" in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_poller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'polymarket_monitor.poller'`.

- [ ] **Step 3: Implement `poller.py`**

`src/polymarket_monitor/poller.py`:

```python
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from .client import fetch_nfl_moneyline_markets
from .detector import MoveDetector

POLL_INTERVAL_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 480.0  # 8 minutes

logger = logging.getLogger("polymarket_monitor")


def run(poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    detector = MoveDetector()
    with httpx.Client(timeout=10.0) as client:
        backoff = poll_interval
        while True:
            ok = poll_once(client, detector)
            if ok:
                backoff = poll_interval
                time.sleep(poll_interval)
            else:
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


def poll_once(client: httpx.Client, detector: MoveDetector) -> bool:
    """Fetch current NFL moneyline prices and feed them to the detector.
    Returns True on a successful fetch, False if the fetch failed (the
    caller backs off before retrying)."""
    now = datetime.now(timezone.utc)
    try:
        snapshots = fetch_nfl_moneyline_markets(client)
    except httpx.HTTPError as exc:
        logger.warning("Polymarket fetch failed: %s", exc)
        return False

    logger.info("Polled %d NFL moneyline markets", len(snapshots))
    for snapshot in snapshots:
        event = detector.observe(
            market_id=snapshot.market_id,
            question=snapshot.question,
            tracked_outcome=snapshot.tracked_outcome,
            price=snapshot.best_ask,
            now=now,
        )
        if event is not None:
            logger.info(
                "MOVE DETECTED: %s (%s) %.3f -> %.3f (%.1f%% relative move) over %s",
                event.question, event.tracked_outcome, event.old_price, event.new_price,
                event.relative_move * 100, event.new_at - event.old_at,
            )
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_poller.py -v`
Expected: PASS — all 3 tests green.

- [ ] **Step 5: Add the runnable entry point**

`src/polymarket_monitor/__main__.py`:

```python
from __future__ import annotations

from .poller import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests green (detector + client unit tests + poller tests; the two `integration`-marked tests skip by default).

- [ ] **Step 7: Verify it actually runs against the live Polymarket API**

Run (via a tool/shell call with a ~45-second timeout — the process loops forever, so let the timeout stop it):

```bash
uv run python -m polymarket_monitor
```

Expected in the captured output: at least one `Polled N NFL moneyline markets` line with `N >= 1` (NFL preseason games are live as of this plan's writing). No tracebacks. `MOVE DETECTED` lines are not expected in a 45-second run (the module needs 10 minutes of history first) — their absence is not a failure.

- [ ] **Step 8: Commit**

```bash
git add src/polymarket_monitor/poller.py src/polymarket_monitor/__main__.py tests/test_poller.py
git commit -m "Add poller loop with backoff and a runnable entry point"
```

---

## Self-Review Notes

- **Spec coverage:** move-detection formula (relative %, 10-min trailing window, sell-side/best-ask reference) → Task 1; market discovery/price fetch → Task 2; continuous poll loop with error backoff → Task 3. Config defaults (poll interval 30s, move threshold 5%, window 10min) are implemented as the literal defaults in code, matching the spec's table. Bookmaker scraping, matching, arb calculation, email, and the orchestrator's cooldown map are explicitly out of scope for this plan — separate follow-up plans per the spec's subsystem list.
- **Placeholder scan:** no TBDs; every step has complete, runnable code.
- **Type consistency:** `MarketSnapshot`, `PriceSample`, and `MoveEvent` field names are identical across `models.py`, `detector.py`, `client.py`, and `poller.py`. `detector.observe()`'s keyword names (`market_id`, `question`, `tracked_outcome`, `price`, `now`) match exactly between Task 1's implementation, Task 3's `poll_once` call site, and Task 3's tests.
