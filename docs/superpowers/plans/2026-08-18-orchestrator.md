# Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `orchestrator/`, the final module: a continuous Polymarket poll loop that, on each detected move, spawns an isolated subprocess that scrapes both bookmakers, matches, computes edges, and sends notifications — with cross-process cooldown tracking via a shared JSON file.

**Architecture:** Four files. `serialization.py` converts a `MoveEvent` to/from a JSON string so it can cross a subprocess boundary as a single CLI argument. `cooldown.py` is a small file-based key-value store (`"market_id|bookmaker" -> ISO timestamp`) that both the poll loop's spawned subprocesses read/write, since cooldown state is only known *after* a subprocess finishes scraping — the long-running poll loop has no visibility into it otherwise. `pipeline.py` is the per-trigger entry point (`python -m orchestrator.pipeline <move-event-json>`): scrape Paddy Power, scrape Novibet, find value bets, skip anything in cooldown, notify, record. `main.py` is structurally the same poll loop as `polymarket_monitor/poller.py`, except each detected move spawns `pipeline.py` as a fire-and-forget subprocess instead of just logging.

**Tech Stack:** Python 3.11+, `uv`, `pytest` (existing `pythonpath = ["src"]` / `testpaths = ["tests"]` / opt-in `integration` marker convention), `subprocess.Popen`/`subprocess.run` (stdlib), reusing `arb_finder`, `matching`, `notifier`, `common`, `polymarket_monitor`, `paddypower_scraper`, `novibet_scraper` exactly as they exist today — no changes to any of those modules.

**Spec:** `docs/superpowers/specs/2026-08-17-nfl-slow-markets-design.md`

## Global Constraints

- Cooldown per (market, bookmaker): **30 minutes** default, config value not hardcoded (spec's config table).
- The scrape→match→arb→notify pipeline runs as an **isolated subprocess per trigger**, never inline in the poll loop — a Playwright hang/crash must never kill polling (spec's Architecture section).
- Cooldown state lives in a **shared JSON file**, not poll-loop memory (user's explicit choice — see design rationale in Task 2). This is orthogonal to the spec's Non-goals "no persistence... across restarts": that non-goal says losing cooldowns on a crash/restart is *accepted*, not that persistence is *forbidden*. The file's actual job is cross-process visibility within one run (poll loop → subprocess), not restart survival — restart survival is an incidental side effect, not a requirement to design for.
- **The automated test suite must never send a real ntfy push notification.** `send_notification` is mocked/monkeypatched in every unit test; the one live-data integration test (Task 3) stubs `send_notification` too, exercising real scraping/matching/arb-computation but never a real push (spec's Testing section: "The ntfy HTTP POST is mocked in tests; the test suite never sends a real push notification").
- Each bookmaker is scraped independently; one bookmaker failing (raises `AllCompetitionsFailedError` / `AllMarketViewGroupsFailedError`) must not block the other, and must not crash the pipeline (spec's Error handling section).
- Follow existing repo conventions exactly: `from __future__ import annotations` at the top of every module, frozen dataclasses for data, `print(..., file=sys.stderr)` for user-facing errors (not raising past module boundaries meant to be non-fatal), pytest test files named `test_<module>_<file>.py` mirroring `src/<module>/<file>.py`, opt-in integration tests via `@pytest.mark.integration` + `pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", ...)`.

---

## Task 1: `orchestrator/serialization.py`

**Files:**
- Create: `src/orchestrator/__init__.py` (empty)
- Create: `src/orchestrator/serialization.py`
- Modify: `pyproject.toml` (register `src/orchestrator` as a wheel package)
- Test: `tests/test_orchestrator_serialization.py`

**Interfaces:**
- Consumes: `polymarket_monitor.models.MoveEvent` — exact fields: `market_id: str`, `question: str`, `tracked_outcome: str`, `old_price: float`, `new_price: float`, `relative_move: float`, `old_at: datetime`, `new_at: datetime`, `game_start_time: str | None = None`.
- Produces: `move_event_to_json(event: MoveEvent) -> str` and `move_event_from_json(text: str) -> MoveEvent`, used by Task 3 (`pipeline.py` parses its CLI argument) and Task 4 (`main.py` serializes before spawning the subprocess).

- [ ] **Step 1: Register the new package in `pyproject.toml`**

Open `pyproject.toml` and change:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/common", "src/polymarket_monitor", "src/paddypower_scraper", "src/notifier", "src/novibet_scraper", "src/matching", "src/arb_finder"]
```

to:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/common", "src/polymarket_monitor", "src/paddypower_scraper", "src/notifier", "src/novibet_scraper", "src/matching", "src/arb_finder", "src/orchestrator"]
```

This must land now (not in a later task) because Task 3 adds a test that invokes `python -m orchestrator.pipeline` as a real OS subprocess — that only resolves if `orchestrator` is an installed (editable) package, which `uv run` establishes from this list.

- [ ] **Step 2: Create the empty package `__init__.py`**

Create `src/orchestrator/__init__.py` with no content (matches every other module in this repo — `src/matching/__init__.py`, `src/arb_finder/__init__.py`, etc. are all empty).

- [ ] **Step 3: Verify the package resolves outside pytest's sys.path trick**

Every other module in this repo is only ever imported through pytest's `pythonpath = ["src"]` config — no prior task has invoked anything via a bare `python -m <package>` subprocess. Task 3 and Task 4 both rely on that working (subprocess-spawning `python -m orchestrator.pipeline`), so confirm it now, before building on it:

Run: `uv run python -c "import orchestrator; print('ok')"`
Expected: prints `ok`. `uv run` auto-syncs the venv against `pyproject.toml` before running, so this confirms the package-list edit in Step 1 took effect as a real editable install, not just as a pytest sys.path entry. If this fails, do not proceed — investigate the `uv sync` / editable-install state before writing more code that depends on it.

- [ ] **Step 4: Write the failing test**

Create `tests/test_orchestrator_serialization.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.serialization import move_event_from_json, move_event_to_json
from polymarket_monitor.models import MoveEvent


def test_round_trip_preserves_all_fields():
    event = MoveEvent(
        market_id="12345",
        question="Commanders vs. Lions",
        tracked_outcome="Commanders",
        old_price=0.55,
        new_price=0.50,
        relative_move=0.0909090909,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
        game_start_time="2026-08-21 00:00:00+00",
    )

    text = move_event_to_json(event)
    result = move_event_from_json(text)

    assert result == event


def test_round_trip_preserves_none_game_start_time():
    event = MoveEvent(
        market_id="1",
        question="Raiders vs. Texans",
        tracked_outcome="Raiders",
        old_price=0.5,
        new_price=0.6,
        relative_move=0.2,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
        game_start_time=None,
    )

    result = move_event_from_json(move_event_to_json(event))

    assert result.game_start_time is None


def test_to_json_returns_a_string():
    event = MoveEvent(
        market_id="1", question="Q", tracked_outcome="T",
        old_price=0.5, new_price=0.5, relative_move=0.0,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert isinstance(move_event_to_json(event), str)
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator_serialization.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'orchestrator'` or `ImportError`)

- [ ] **Step 6: Write the implementation**

Create `src/orchestrator/serialization.py`:

```python
"""Serialize/deserialize a MoveEvent to cross the subprocess boundary as
a single JSON string CLI argument (orchestrator/main.py's
trigger_pipeline spawns orchestrator/pipeline.py with this string)."""

from __future__ import annotations

import json
from datetime import datetime

from polymarket_monitor.models import MoveEvent


def move_event_to_json(event: MoveEvent) -> str:
    return json.dumps(
        {
            "market_id": event.market_id,
            "question": event.question,
            "tracked_outcome": event.tracked_outcome,
            "old_price": event.old_price,
            "new_price": event.new_price,
            "relative_move": event.relative_move,
            "old_at": event.old_at.isoformat(),
            "new_at": event.new_at.isoformat(),
            "game_start_time": event.game_start_time,
        }
    )


def move_event_from_json(text: str) -> MoveEvent:
    data = json.loads(text)
    return MoveEvent(
        market_id=data["market_id"],
        question=data["question"],
        tracked_outcome=data["tracked_outcome"],
        old_price=data["old_price"],
        new_price=data["new_price"],
        relative_move=data["relative_move"],
        old_at=datetime.fromisoformat(data["old_at"]),
        new_at=datetime.fromisoformat(data["new_at"]),
        game_start_time=data.get("game_start_time"),
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_serialization.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/orchestrator/__init__.py src/orchestrator/serialization.py tests/test_orchestrator_serialization.py
git commit -m "feat(orchestrator): add MoveEvent JSON serialization"
```

---

## Task 2: `orchestrator/cooldown.py`

**Files:**
- Create: `src/orchestrator/cooldown.py`
- Test: `tests/test_orchestrator_cooldown.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `default_cooldown_path() -> Path`, `load_cooldowns(path: Path) -> dict[str, str]`, `save_cooldowns(path: Path, cooldowns: dict[str, str]) -> None`, `is_in_cooldown(cooldowns: dict[str, str], market_id: str, bookmaker: str, now: datetime, window: timedelta = DEFAULT_COOLDOWN) -> bool`, `record_alert(cooldowns: dict[str, str], market_id: str, bookmaker: str, now: datetime) -> None`, `DEFAULT_COOLDOWN: timedelta` (30 minutes). All consumed by Task 3's `pipeline.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_cooldown.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.cooldown import (
    is_in_cooldown,
    load_cooldowns,
    record_alert,
    save_cooldowns,
)

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def test_is_in_cooldown_false_when_key_absent():
    assert is_in_cooldown({}, "market-1", "Paddy Power", NOW) is False


def test_is_in_cooldown_true_within_window():
    cooldowns = {"market-1|Paddy Power": (NOW - timedelta(minutes=10)).isoformat()}
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is True


def test_is_in_cooldown_false_outside_window():
    cooldowns = {"market-1|Paddy Power": (NOW - timedelta(minutes=31)).isoformat()}
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is False


def test_is_in_cooldown_respects_custom_window():
    cooldowns = {"market-1|Paddy Power": (NOW - timedelta(minutes=5)).isoformat()}
    assert (
        is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW, window=timedelta(minutes=1))
        is False
    )


def test_is_in_cooldown_false_on_malformed_timestamp():
    cooldowns = {"market-1|Paddy Power": "not-a-timestamp"}
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is False


def test_is_in_cooldown_distinguishes_bookmakers():
    cooldowns = {"market-1|Paddy Power": NOW.isoformat()}
    assert is_in_cooldown(cooldowns, "market-1", "Novibet", NOW) is False


def test_is_in_cooldown_distinguishes_markets():
    cooldowns = {"market-1|Paddy Power": NOW.isoformat()}
    assert is_in_cooldown(cooldowns, "market-2", "Paddy Power", NOW) is False


def test_record_alert_then_is_in_cooldown_round_trips_true():
    cooldowns: dict[str, str] = {}
    record_alert(cooldowns, "market-1", "Paddy Power", NOW)
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is True


def test_load_cooldowns_missing_file_returns_empty_dict(tmp_path):
    path = tmp_path / "cooldown.json"
    assert load_cooldowns(path) == {}


def test_load_cooldowns_corrupt_json_returns_empty_dict(tmp_path):
    path = tmp_path / "cooldown.json"
    path.write_text("{not valid json")
    assert load_cooldowns(path) == {}


def test_load_cooldowns_non_object_json_returns_empty_dict(tmp_path):
    path = tmp_path / "cooldown.json"
    path.write_text("[1, 2, 3]")
    assert load_cooldowns(path) == {}


def test_save_then_load_round_trips_and_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "cooldown.json"
    cooldowns = {"market-1|Paddy Power": NOW.isoformat()}

    save_cooldowns(path, cooldowns)
    result = load_cooldowns(path)

    assert result == cooldowns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator_cooldown.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'orchestrator.cooldown'`)

- [ ] **Step 3: Write the implementation**

Create `src/orchestrator/cooldown.py`:

```python
"""File-based cooldown tracking: has this (market, bookmaker) pair
already alerted recently? State lives in a small shared JSON file
rather than in the long-lived poll loop's memory, because cooldown
outcomes are only known AFTER a subprocess (orchestrator/pipeline.py)
finishes scraping and computing edges — the poll loop has no visibility
into that without this file. See the plan's Global Constraints for why
this doesn't conflict with the spec's "no cross-restart persistence"
non-goal."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_COOLDOWN = timedelta(minutes=30)


def default_cooldown_path() -> Path:
    return Path.home() / ".nfl-slow-markets" / "cooldown.json"


def load_cooldowns(path: Path) -> dict[str, str]:
    """Missing file, unreadable file, corrupt JSON, or JSON that isn't an
    object all fail open to an empty dict (never crash the pipeline)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_cooldowns(path: Path, cooldowns: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cooldowns, indent=2))


def _key(market_id: str, bookmaker: str) -> str:
    return f"{market_id}|{bookmaker}"


def is_in_cooldown(
    cooldowns: dict[str, str],
    market_id: str,
    bookmaker: str,
    now: datetime,
    window: timedelta = DEFAULT_COOLDOWN,
) -> bool:
    raw = cooldowns.get(_key(market_id, bookmaker))
    if raw is None:
        return False
    try:
        last_alerted = datetime.fromisoformat(raw)
    except ValueError:
        return False
    return now - last_alerted < window


def record_alert(cooldowns: dict[str, str], market_id: str, bookmaker: str, now: datetime) -> None:
    cooldowns[_key(market_id, bookmaker)] = now.isoformat()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_cooldown.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/cooldown.py tests/test_orchestrator_cooldown.py
git commit -m "feat(orchestrator): add file-based cooldown tracking"
```

---

## Task 3: `orchestrator/pipeline.py`

**Files:**
- Create: `src/orchestrator/pipeline.py`
- Test: `tests/test_orchestrator_pipeline.py`
- Test: `tests/test_pipeline_integration.py`

**Interfaces:**
- Consumes:
  - `orchestrator.serialization.move_event_from_json(text: str) -> MoveEvent` (Task 1)
  - `orchestrator.cooldown.{default_cooldown_path, load_cooldowns, save_cooldowns, is_in_cooldown, record_alert}` (Task 2)
  - `common.credentials.{default_credentials_path, load_credentials}` — `load_credentials(path) -> Credentials`, raises `ValueError` on any failure
  - `arb_finder.finder.find_value_bets(move, paddypower_games, novibet_games, min_edge=DEFAULT_MIN_EDGE) -> list[ValueBetAlert]`
  - `matching.adapters.{from_paddypower, from_novibet}` — each takes one bookmaker's native game model and returns a `matching.models.BookmakerGame`
  - `notifier.formatting.format_alert(alert: ValueBetAlert) -> NtfyMessage`
  - `notifier.ntfy.send_notification(message: NtfyMessage, topic: str, client=None) -> bool` — never raises
  - `paddypower_scraper.browser.BrowserSession` (context manager) + `paddypower_scraper.scraper.{scrape_nfl_moneylines, AllCompetitionsFailedError}` — `scrape_nfl_moneylines(session, competition_ids=DEFAULT_COMPETITION_IDS) -> list[NFLGameOdds]`
  - `novibet_scraper.browser.BrowserSession` + `novibet_scraper.scraper.{scrape_nfl_moneylines, AllMarketViewGroupsFailedError}` — same shape
  - `polymarket_monitor.client.fetch_nfl_moneyline_markets(client=None) -> list[MarketSnapshot]` (integration test only)
- Produces: `main(argv: list[str] | None = None) -> int`, module-level names `_scrape_paddypower`, `_scrape_novibet`, `find_value_bets`, `default_cooldown_path`, `load_credentials`, `send_notification` — all monkeypatchable by tests and by Task 4 is NOT dependent on any of these (Task 4 only spawns this module as a subprocess, never imports it).

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_orchestrator_pipeline.py`:

```python
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone

from common.credentials import Credentials
from notifier.models import ValueBetAlert
from orchestrator import pipeline
from orchestrator.cooldown import load_cooldowns, save_cooldowns
from orchestrator.serialization import move_event_to_json
from polymarket_monitor.models import MoveEvent

MOVE = MoveEvent(
    market_id="market-1",
    question="Commanders vs. Lions",
    tracked_outcome="Commanders",
    old_price=0.55,
    new_price=0.50,
    relative_move=0.0909090909,
    old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
    game_start_time="2026-08-21 00:00:00+00",
)

ALERT = ValueBetAlert(
    game_name="Commanders vs. Lions",
    team_name="Commanders",
    bookmaker="Paddy Power",
    decimal_odds=2.10,
    polymarket_old_price=0.55,
    polymarket_new_price=0.50,
    polymarket_relative_move=-0.0909090909,
    edge=0.05,
)


def _patch_common(monkeypatch, tmp_path, *, alerts, sends_ok=True, credentials_ok=True):
    monkeypatch.setattr(pipeline, "_scrape_paddypower", lambda: [])
    monkeypatch.setattr(pipeline, "_scrape_novibet", lambda: [])
    monkeypatch.setattr(pipeline, "find_value_bets", lambda move, pp, nb: alerts)
    monkeypatch.setattr(pipeline, "default_cooldown_path", lambda: tmp_path / "cooldown.json")
    monkeypatch.setattr(pipeline, "send_notification", lambda message, topic: sends_ok)
    if credentials_ok:
        monkeypatch.setattr(
            pipeline, "load_credentials", lambda path: Credentials(ntfy_topic="test-topic")
        )
    else:
        def _raise(path):
            raise ValueError("credentials file not found")

        monkeypatch.setattr(pipeline, "load_credentials", _raise)


def test_main_requires_exactly_one_argument(capsys):
    assert pipeline.main([]) == 1
    assert "usage" in capsys.readouterr().err

    assert pipeline.main(["a", "b"]) == 1


def test_main_returns_1_when_credentials_missing(monkeypatch, tmp_path, capsys):
    _patch_common(monkeypatch, tmp_path, alerts=[], credentials_ok=False)

    result = pipeline.main([move_event_to_json(MOVE)])

    assert result == 1
    assert "credentials" in capsys.readouterr().err.lower()


def test_main_returns_0_and_sends_nothing_when_no_alerts(monkeypatch, tmp_path, capsys):
    _patch_common(monkeypatch, tmp_path, alerts=[])

    result = pipeline.main([move_event_to_json(MOVE)])

    assert result == 0
    assert "no value bets found" in capsys.readouterr().out
    assert not (tmp_path / "cooldown.json").exists()


def test_main_sends_and_records_alert_not_in_cooldown(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, alerts=[ALERT])
    sent_messages = []
    monkeypatch.setattr(
        pipeline,
        "send_notification",
        lambda message, topic: sent_messages.append((message, topic)) or True,
    )

    result = pipeline.main([move_event_to_json(MOVE)])

    assert result == 0
    assert len(sent_messages) == 1
    assert sent_messages[0][1] == "test-topic"
    cooldowns = load_cooldowns(tmp_path / "cooldown.json")
    assert "market-1|Paddy Power" in cooldowns


def test_main_skips_alert_already_in_cooldown(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    save_cooldowns(tmp_path / "cooldown.json", {"market-1|Paddy Power": now.isoformat()})
    _patch_common(monkeypatch, tmp_path, alerts=[ALERT])
    sent_messages = []
    monkeypatch.setattr(
        pipeline,
        "send_notification",
        lambda message, topic: sent_messages.append((message, topic)) or True,
    )

    result = pipeline.main([move_event_to_json(MOVE)])

    assert result == 0
    assert sent_messages == []


def test_main_does_not_record_alert_when_send_fails(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, alerts=[ALERT], sends_ok=False)

    result = pipeline.main([move_event_to_json(MOVE)])

    assert result == 0
    cooldowns = load_cooldowns(tmp_path / "cooldown.json")
    assert cooldowns == {}


def test_module_is_invocable_via_python_dash_m():
    """Confirms `orchestrator` resolves as an installed package under -m,
    exactly how orchestrator/main.py's trigger_pipeline (Task 4) invokes
    it. No network access — just argv validation."""
    result = subprocess.run(
        [sys.executable, "-m", "orchestrator.pipeline"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "usage" in result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator_pipeline.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'orchestrator.pipeline'`)

- [ ] **Step 3: Write the implementation**

Create `src/orchestrator/pipeline.py`:

```python
"""One trigger's worth of work: scrape both bookmakers, match against a
detected Polymarket move, compute edges, and send notifications for
anything not already in cooldown.

Runs as its own OS process per invocation (see orchestrator/main.py's
trigger_pipeline, which spawns `python -m orchestrator.pipeline
<move-event-json>` via subprocess.Popen) so a Playwright hang or crash
here can never take down the continuously-running Polymarket poll loop.

Scrapes Paddy Power and Novibet sequentially, not concurrently. Each
BrowserSession's Cloudflare warmup + fetch takes on the order of
10-30s, so a trigger-to-alert round trip is roughly 20-60s. Running the
two scrapers concurrently would roughly halve that — each BrowserSession
already creates its own independent sync_playwright() instance with no
shared state, so it's plausible — but Playwright's sync API under
threading isn't exercised anywhere else in this codebase, and this is
the last module of the project. Deferred as a follow-up rather than
risked here; sequential is simple and definitely correct."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from arb_finder.finder import find_value_bets
from common.credentials import default_credentials_path, load_credentials
from matching.adapters import from_novibet, from_paddypower
from matching.models import BookmakerGame
from notifier.formatting import format_alert
from notifier.ntfy import send_notification
from novibet_scraper.browser import BrowserSession as NovibetBrowserSession
from novibet_scraper.scraper import AllMarketViewGroupsFailedError
from novibet_scraper.scraper import scrape_nfl_moneylines as scrape_novibet
from paddypower_scraper.browser import BrowserSession as PaddyPowerBrowserSession
from paddypower_scraper.scraper import AllCompetitionsFailedError
from paddypower_scraper.scraper import scrape_nfl_moneylines as scrape_paddypower

from .cooldown import (
    default_cooldown_path,
    is_in_cooldown,
    load_cooldowns,
    record_alert,
    save_cooldowns,
)
from .serialization import move_event_from_json


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m orchestrator.pipeline <move-event-json>", file=sys.stderr)
        return 1
    move = move_event_from_json(argv[0])

    try:
        creds = load_credentials(default_credentials_path())
    except ValueError as exc:
        print(f"orchestrator: {exc}", file=sys.stderr)
        return 1

    paddypower_games = _scrape_paddypower()
    novibet_games = _scrape_novibet()
    alerts = find_value_bets(move, paddypower_games, novibet_games)

    if not alerts:
        print(f"orchestrator: no value bets found for {move.question}")
        return 0

    cooldown_path = default_cooldown_path()
    cooldowns = load_cooldowns(cooldown_path)
    now = datetime.now(timezone.utc)
    sent = 0
    for alert in alerts:
        if is_in_cooldown(cooldowns, move.market_id, alert.bookmaker, now):
            print(f"orchestrator: {move.market_id}/{alert.bookmaker} in cooldown, skipping")
            continue
        message = format_alert(alert)
        if send_notification(message, creds.ntfy_topic):
            record_alert(cooldowns, move.market_id, alert.bookmaker, now)
            sent += 1
        else:
            print(f"orchestrator: failed to send notification for {alert.bookmaker}", file=sys.stderr)

    save_cooldowns(cooldown_path, cooldowns)
    print(f"orchestrator: sent {sent}/{len(alerts)} alert(s) for {move.question}")
    return 0


def _scrape_paddypower() -> list[BookmakerGame]:
    try:
        with PaddyPowerBrowserSession() as session:
            games = scrape_paddypower(session)
    except AllCompetitionsFailedError as exc:
        print(f"orchestrator: paddypower scrape failed: {exc}", file=sys.stderr)
        return []
    return [from_paddypower(g) for g in games]


def _scrape_novibet() -> list[BookmakerGame]:
    try:
        with NovibetBrowserSession() as session:
            games = scrape_novibet(session)
    except AllMarketViewGroupsFailedError as exc:
        print(f"orchestrator: novibet scrape failed: {exc}", file=sys.stderr)
        return []
    return [from_novibet(g) for g in games]


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_pipeline.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Write the live-data integration test**

Create `tests/test_pipeline_integration.py`:

```python
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
```

- [ ] **Step 6: Run the integration test live**

Run: `RUN_INTEGRATION=1 uv run pytest tests/test_pipeline_integration.py -v -m integration -s`
Expected: PASS. Read the printed stdout (`-s`) to confirm it reports either `"orchestrator: no value bets found for ..."` or `"orchestrator: sent N/M alert(s) for ..."` — either is a valid outcome (it depends on real current bookmaker prices), but the process must exit 0 with no unhandled traceback. If it fails, read the failure output before touching any code — a missing `~/.nfl-slow-markets/credentials.json` or a bookmaker site layout change are both plausible environment causes, not necessarily a bug in this task's code.

- [ ] **Step 7: Run the full non-integration suite to confirm nothing else broke**

Run: `uv run pytest -v`
Expected: all non-integration tests PASS, integration tests skipped (unless `RUN_INTEGRATION=1` is still set).

- [ ] **Step 8: Commit**

```bash
git add src/orchestrator/pipeline.py tests/test_orchestrator_pipeline.py tests/test_pipeline_integration.py
git commit -m "feat(orchestrator): add scrape-match-arb-notify pipeline entry point"
```

---

## Task 4: `orchestrator/main.py` + `orchestrator/__main__.py`

**Files:**
- Create: `src/orchestrator/main.py`
- Create: `src/orchestrator/__main__.py`
- Modify: `pyproject.toml` (add `orchestrator` console script entry)
- Test: `tests/test_orchestrator_main.py`

**Interfaces:**
- Consumes:
  - `orchestrator.serialization.move_event_to_json(event: MoveEvent) -> str` (Task 1)
  - `polymarket_monitor.client.fetch_nfl_moneyline_markets(client=None) -> list[MarketSnapshot]`
  - `polymarket_monitor.detector.MoveDetector` — `.observe(market_id, question, tracked_outcome, price, now, game_start_time=None) -> MoveEvent | None`
  - `polymarket_monitor.models.MoveEvent`
- Produces: `run(poll_interval: float = POLL_INTERVAL_SECONDS) -> None`, `poll_once(client, detector) -> bool`, `trigger_pipeline(event: MoveEvent) -> subprocess.Popen | None` — this task is terminal; nothing later consumes its output. `orchestrator/__main__.py` is what the spec's Deployment section's `uv run python -m orchestrator` invokes.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_main.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from orchestrator import main as orchestrator_main
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
        market_id="1",
        question="Raiders vs. Texans",
        tracked_outcome="Raiders",
        best_ask=0.51,
        game_start_time="2026-08-21 00:00:00+00",
    )
    monkeypatch.setattr(orchestrator_main, "fetch_nfl_moneyline_markets", lambda client: [snapshot])
    detector = _RecordingDetector()

    ok = orchestrator_main.poll_once(client=object(), detector=detector)

    assert ok is True
    assert len(detector.calls) == 1
    call = detector.calls[0]
    assert call["market_id"] == "1"
    assert call["question"] == "Raiders vs. Texans"
    assert call["tracked_outcome"] == "Raiders"
    assert call["price"] == 0.51


def test_poll_once_returns_false_and_logs_warning_on_fetch_error(monkeypatch, caplog):
    def _raise(client):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(orchestrator_main, "fetch_nfl_moneyline_markets", _raise)

    with caplog.at_level(logging.WARNING):
        ok = orchestrator_main.poll_once(client=object(), detector=MoveDetector())

    assert ok is False
    assert "Polymarket fetch failed" in caplog.text


def test_poll_once_triggers_pipeline_on_detected_move(monkeypatch):
    snapshot = MarketSnapshot(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        best_ask=0.60, game_start_time=None,
    )
    monkeypatch.setattr(orchestrator_main, "fetch_nfl_moneyline_markets", lambda client: [snapshot])
    triggered = []
    monkeypatch.setattr(orchestrator_main, "trigger_pipeline", lambda event: triggered.append(event))

    ok = orchestrator_main.poll_once(client=object(), detector=_AlwaysMovesDetector())

    assert ok is True
    assert len(triggered) == 1
    assert triggered[0].question == "Raiders vs. Texans"


def test_poll_once_does_not_trigger_pipeline_when_no_move(monkeypatch):
    snapshot = MarketSnapshot(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        best_ask=0.51, game_start_time=None,
    )
    monkeypatch.setattr(orchestrator_main, "fetch_nfl_moneyline_markets", lambda client: [snapshot])
    triggered = []
    monkeypatch.setattr(orchestrator_main, "trigger_pipeline", lambda event: triggered.append(event))

    orchestrator_main.poll_once(client=object(), detector=_RecordingDetector())

    assert triggered == []


def test_trigger_pipeline_spawns_subprocess_with_serialized_event(monkeypatch):
    captured = {}

    class _FakePopen:
        def __init__(self, args):
            captured["args"] = args

    monkeypatch.setattr(orchestrator_main.subprocess, "Popen", _FakePopen)

    event = MoveEvent(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        old_price=0.50, new_price=0.60, relative_move=0.20,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
    )

    orchestrator_main.trigger_pipeline(event)

    args = captured["args"]
    assert args[0] == orchestrator_main.sys.executable
    assert args[1:3] == ["-m", "orchestrator.pipeline"]
    assert "Raiders vs. Texans" in args[3]


def test_trigger_pipeline_returns_none_and_logs_on_spawn_failure(monkeypatch, caplog):
    def _raise(args):
        raise OSError("no such file")

    monkeypatch.setattr(orchestrator_main.subprocess, "Popen", _raise)
    event = MoveEvent(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        old_price=0.50, new_price=0.60, relative_move=0.20,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
    )

    with caplog.at_level(logging.WARNING):
        result = orchestrator_main.trigger_pipeline(event)

    assert result is None
    assert "Failed to spawn" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator_main.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'orchestrator.main'`)

- [ ] **Step 3: Write the implementation**

Create `src/orchestrator/main.py`:

```python
"""Continuous Polymarket poll loop. On each detected move, spawns the
scrape -> match -> arb -> notify pipeline (orchestrator/pipeline.py) as
an isolated subprocess and returns immediately — never blocks waiting
for a trigger to finish. Structurally the same loop as
polymarket_monitor/poller.py, except a detected move spawns a pipeline
run instead of only logging."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from datetime import datetime, timezone

import httpx

from polymarket_monitor.client import fetch_nfl_moneyline_markets
from polymarket_monitor.detector import MoveDetector
from polymarket_monitor.models import MoveEvent

from .serialization import move_event_to_json

POLL_INTERVAL_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 480.0  # 8 minutes

logger = logging.getLogger("orchestrator")


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
    """Fetch current NFL moneyline prices, feed them to the detector, and
    spawn the pipeline for each detected move. Returns True on a
    successful fetch, False if the fetch failed (the caller backs off
    before retrying)."""
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
            game_start_time=snapshot.game_start_time,
        )
        if event is not None:
            logger.info(
                "MOVE DETECTED: %s (%s) %.3f -> %.3f (%.1f%% relative move) over %s",
                event.question,
                event.tracked_outcome,
                event.old_price,
                event.new_price,
                event.relative_move * 100,
                event.new_at - event.old_at,
            )
            trigger_pipeline(event)
    return True


def trigger_pipeline(event: MoveEvent) -> subprocess.Popen | None:
    """Fire-and-forget: spawn `python -m orchestrator.pipeline
    <move-event-json>` as a subprocess and return immediately. Inherits
    the parent's stdout/stderr (no redirection), so pipeline output
    interleaves with poll-loop logging in the same terminal. Never
    raises — a failure to even spawn the subprocess is logged and
    swallowed, matching this module's "a pipeline problem can never
    take down polling" contract."""
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "orchestrator.pipeline", move_event_to_json(event)]
        )
    except OSError as exc:
        logger.warning("Failed to spawn orchestrator pipeline: %s", exc)
        return None
```

Create `src/orchestrator/__main__.py`:

```python
from __future__ import annotations

from .main import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Add the console script entry**

Open `pyproject.toml` and change:

```toml
[project.scripts]
polymarket-monitor = "polymarket_monitor.poller:run"
```

to:

```toml
[project.scripts]
polymarket-monitor = "polymarket_monitor.poller:run"
orchestrator = "orchestrator.main:run"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_main.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest -v`
Expected: all non-integration tests PASS, integration tests skipped by default.

- [ ] **Step 7: Manually verify `python -m orchestrator` starts the poll loop**

Run: `timeout 5 uv run python -m orchestrator || true`
Expected: within the 5-second window, at least one log line like `Polled N NFL moneyline markets` appears (confirms `__main__.py` → `run()` → `poll_once()` wiring resolves and makes a real Polymarket API call), then the process is killed by `timeout` — this is a manual smoke check, not a permanent test (a poll loop is `while True` by design and would otherwise hang the test suite).

- [ ] **Step 8: Commit**

```bash
git add src/orchestrator/main.py src/orchestrator/__main__.py pyproject.toml tests/test_orchestrator_main.py
git commit -m "feat(orchestrator): add poll loop that spawns the pipeline on detected moves"
```

---

## Final Integration Check

After all four tasks are complete and individually reviewed, before handing off to the final whole-branch review:

- [ ] Run `uv run pytest -v` — full suite passes, integration tests skipped by default.
- [ ] Run `RUN_INTEGRATION=1 uv run pytest -v -m integration` — all opt-in integration tests pass, including `test_pipeline_runs_end_to_end_against_live_data` and the pre-existing Polymarket/Paddy Power/Novibet live tests.
- [ ] Confirm `git grep -n "ntfy_topic" -- '*.py' '*.md'` shows no literal topic value committed anywhere (matches the discipline established after the earlier leaked-secret incident).
