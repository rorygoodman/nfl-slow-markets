# Arb Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `arb_finder` module — joins a detected Polymarket price move (`polymarket_monitor.MoveEvent`) to matched bookmaker prices (via the already-built `matching` module), computes the value-bet edge per bookmaker leg, filters by a minimum edge threshold, and ranks the results into `notifier.models.ValueBetAlert` objects ready to send. This is the module that finally answers "is there actually a profitable bet here."

**Architecture:** A pure `calculator.py` computes `value_bet_edge(decimal_odds, true_prob) -> float` per the spec's formula. `finder.py` orchestrates: for each bookmaker independently (non-fatal — one bookmaker's absence never blocks the other), call `matching.match_game` + `matching.team_price_for` to find the moved team's current price, compute the edge, and — if it clears `min_edge` — build a `ValueBetAlert`. Results are ranked by edge descending. **Before any of that can work, `polymarket_monitor.MoveEvent` needs one small addition**: it currently doesn't carry the market's kickoff time, which `matching.match_game` requires as an argument — a gap found and correctly scoped to this plan by `matching`'s own final review. Task 1 threads `game_start_time` through `MoveDetector.observe()` into a new, backward-compatible `MoveEvent` field, using the already-existing `MarketSnapshot.game_start_time` (already captured by `polymarket_monitor.client`, just not yet propagated).

**Tech Stack:** Python ≥3.11, `uv`, `pytest`. No new dependencies, no network I/O.

**Spec:** `docs/superpowers/specs/2026-08-17-nfl-slow-markets-design.md`

## Global Constraints

- Python ≥3.11, managed with `uv`.
- `value_bet_edge(decimal_odds: float, true_prob: float) -> float` returns exactly `decimal_odds * true_prob - 1`, per the spec.
- `true_prob` is always the Polymarket **sell-side price at trigger time** — `MoveEvent.new_price` (the post-move price), never `old_price`. This matches the spec's architecture diagram exactly and is the whole reason the tool exists (checking a stale bookmaker price against the *new* fair price).
- **`MoveEvent.relative_move` is an unsigned magnitude** (computed via `abs(...)` in `polymarket_monitor/detector.py` — verified by reading the existing, already-merged code). `ValueBetAlert.polymarket_relative_move` must be **signed** (positive if the price rose, negative if it fell) — `notifier`'s own test suite explicitly exercises a negative value and documents the `{:+.1%}` display format. `arb_finder` must compute this itself as `(move.new_price - move.old_price) / move.old_price`, never pass `move.relative_move` straight through — that would silently always show a move as positive, even when the team's price fell.
- Each bookmaker leg is checked and filtered **independently** — a bookmaker with no match (`matching.match_game` returns `None`) or a below-threshold edge is silently skipped for that leg only, never treated as an error, and never blocks the other bookmaker's leg. Matches this project's established non-fatal-per-bookmaker philosophy.
- Task 1's change to `polymarket_monitor` (an already-merged, already-reviewed module) must be **strictly additive and backward-compatible** — every existing test in `tests/test_detector.py` and `tests/test_poller.py` must keep passing completely unchanged, with zero edits to those files. The new field/parameter defaults to `None`.
- Every new top-level package under `src/` added to `pyproject.toml`'s wheel `packages` list.
- This plan covers `arb_finder` (plus the one small `polymarket_monitor` prerequisite fix). The `orchestrator` that actually wires the continuous poll loop to a scrape-trigger to this module to `notifier` remains out of scope, covered by the next plan.

---

## Verified existing code (read directly from this repo before writing this plan — not assumptions)

- `polymarket_monitor/models.py`'s `MarketSnapshot` already has `game_start_time: str | None` — captured by `client.py`, just never threaded past `poller.py`'s call to `detector.observe(...)`.
- `polymarket_monitor/detector.py`'s `MoveDetector.observe(self, market_id, question, tracked_outcome, price, now)` has no kickoff-time parameter; `MoveEvent` has no `game_start_time` field.
- `polymarket_monitor/poller.py`'s `poll_once` already has `snapshot` in scope at the exact call site (`snapshot.game_start_time` is available, just not passed).
- `notifier/models.py`'s `ValueBetAlert(game_name, team_name, bookmaker, decimal_odds, polymarket_old_price, polymarket_new_price, polymarket_relative_move, edge)` — all fields required, no defaults — already has a docstring stating "Future modules (arb_finder, orchestrator) construct this; notifier only consumes it." This plan is that future module; no new output type is needed.
- `matching/matcher.py`'s `match_game(polymarket_question, polymarket_kickoff, bookmaker_games) -> BookmakerGame | None` and `team_price_for(game, team_name) -> BookmakerTeamPrice | None` — both already fail closed (`None` on any ambiguity, never raise) and already have a 30-minute kickoff tolerance (fixed in `matching`'s own final review) — `arb_finder` can call these directly with no extra defensive wrapping needed.

---

### Task 1: Thread kickoff time through `polymarket_monitor.MoveEvent` (backward-compatible, TDD)

**Files:**
- Modify: `src/polymarket_monitor/models.py`
- Modify: `src/polymarket_monitor/detector.py`
- Modify: `src/polymarket_monitor/poller.py`
- Test: `tests/test_detector.py` (add new tests only — do not edit or remove any existing test)
- Test: `tests/test_poller.py` (add new tests only — do not edit or remove any existing test)

**Interfaces:**
- Produces (used by Task 3, and by the future `orchestrator` plan):
  - `models.MoveEvent` gains `game_start_time: str | None = None` (last field, defaulted — every existing construction of `MoveEvent` without this argument keeps working unchanged)
  - `detector.MoveDetector.observe(...)` gains `game_start_time: str | None = None` (last parameter, defaulted)
  - `poller.poll_once` now passes `game_start_time=snapshot.game_start_time` to `detector.observe(...)`

- [ ] **Step 1: Run the existing test suite to record the baseline**

Run: `uv run pytest tests/test_detector.py tests/test_poller.py -v`
Expected: PASS — all existing tests green (this is your baseline; every one of these must still pass unchanged after your edits).

- [ ] **Step 2: Write the new failing tests**

Add to `tests/test_detector.py` (append — do not touch any existing test in this file):

```python
def test_observe_without_game_start_time_defaults_to_none():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.60, T0 + timedelta(minutes=10)
    )
    assert event is not None
    assert event.game_start_time is None


def test_observe_threads_game_start_time_into_the_move_event():
    detector = MoveDetector()
    detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.50, T0,
        game_start_time="2026-08-21 00:00:00+00",
    )
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.60, T0 + timedelta(minutes=10),
        game_start_time="2026-08-21 00:00:00+00",
    )
    assert event is not None
    assert event.game_start_time == "2026-08-21 00:00:00+00"
```

Add to `tests/test_poller.py` (append — do not touch any existing test in this file):

```python
def test_poll_once_passes_game_start_time_through_to_the_detector(monkeypatch):
    snapshot = MarketSnapshot(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        best_ask=0.51, game_start_time="2026-08-21 00:00:00+00",
    )
    monkeypatch.setattr(poller, "fetch_nfl_moneyline_markets", lambda client: [snapshot])
    detector = _RecordingDetector()

    poller.poll_once(client=object(), detector=detector)

    assert detector.calls[0]["game_start_time"] == "2026-08-21 00:00:00+00"
```

(`_RecordingDetector`, `MarketSnapshot`, and `poller` are already imported/defined in this test file — reuse them, don't redefine.)

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_detector.py tests/test_poller.py -v`
Expected: the two new `test_detector.py` tests FAIL with `TypeError: observe() got an unexpected keyword argument 'game_start_time'` (or the event lacks the attribute); the new `test_poller.py` test FAILS with a `KeyError` (`detector.calls[0]` has no `"game_start_time"` key) — all pre-existing tests in both files still PASS unchanged.

- [ ] **Step 4: Add the field to `MoveEvent`**

In `src/polymarket_monitor/models.py`, add one field to the end of the `MoveEvent` dataclass (after `new_at`):

```python
    game_start_time: "str | None" = None
```

- [ ] **Step 5: Thread the parameter through `MoveDetector.observe`**

In `src/polymarket_monitor/detector.py`:
- Add `game_start_time: "str | None" = None` as the last parameter of `observe(...)`'s signature.
- Add `game_start_time=game_start_time,` as the last argument in the `MoveEvent(...)` construction at the end of the method.

- [ ] **Step 6: Wire it through the poll loop**

In `src/polymarket_monitor/poller.py`, in `poll_once`, add `game_start_time=snapshot.game_start_time,` as an argument to the existing `detector.observe(...)` call.

- [ ] **Step 7: Run the tests to verify everything passes**

Run: `uv run pytest tests/test_detector.py tests/test_poller.py -v`
Expected: PASS — every pre-existing test AND the new tests all green.

- [ ] **Step 8: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests green across the whole project, no regressions anywhere.

- [ ] **Step 9: Commit**

```bash
git add src/polymarket_monitor/models.py src/polymarket_monitor/detector.py src/polymarket_monitor/poller.py tests/test_detector.py tests/test_poller.py
git commit -m "Thread kickoff time through MoveEvent (prerequisite for matching)"
```

---

### Task 2: `arb_finder.calculator` (pure, TDD)

**Files:**
- Create: `src/arb_finder/__init__.py`
- Create: `src/arb_finder/calculator.py`
- Modify: `pyproject.toml` (add `"src/arb_finder"` to the wheel `packages` list)
- Test: `tests/test_arb_finder_calculator.py`

**Interfaces:**
- Produces (used by Task 3):
  - `calculator.value_bet_edge(decimal_odds: float, true_prob: float) -> float`

- [ ] **Step 1: Create the project scaffolding**

Create empty `src/arb_finder/__init__.py`. Add `"src/arb_finder"` to `pyproject.toml`'s `[tool.hatch.build.targets.wheel] packages` list.

- [ ] **Step 2: Write the failing tests**

`tests/test_arb_finder_calculator.py`:

```python
from __future__ import annotations

from arb_finder.calculator import value_bet_edge


def test_positive_edge():
    # decimal_odds=2.00, true_prob=0.525 -> 2.00*0.525-1 = +0.05
    assert round(value_bet_edge(2.00, 0.525), 6) == 0.05


def test_negative_edge():
    # decimal_odds=2.10, true_prob=0.40 -> 2.10*0.40-1 = -0.16
    assert round(value_bet_edge(2.10, 0.40), 6) == -0.16


def test_zero_edge_at_fair_odds():
    # decimal_odds exactly matching true_prob's fair price -> edge is 0
    assert round(value_bet_edge(2.0, 0.50), 6) == 0.0


def test_real_captured_data_negative_edge():
    # Real Commanders/Lions data: Paddy Power backs Commanders at 2.6,
    # Polymarket's post-move Commanders price was 0.36 -> a bad bet.
    assert round(value_bet_edge(2.6, 0.36), 6) == round(2.6 * 0.36 - 1, 6)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_arb_finder_calculator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'arb_finder.calculator'`.

- [ ] **Step 4: Implement `calculator.py`**

`src/arb_finder/calculator.py`:

```python
"""Pure value-bet edge math. See the design spec for the formula's
derivation — this is the whole reason the tool exists."""

from __future__ import annotations


def value_bet_edge(decimal_odds: float, true_prob: float) -> float:
    """Expected value per £1 staked, backing this bookmaker price against
    `true_prob` (the reference "fair" probability — this project always
    uses Polymarket's post-move sell-side price for this). Positive means
    a value bet; negative means the bookmaker price is worse than fair."""
    return decimal_odds * true_prob - 1
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_arb_finder_calculator.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests green, no regressions.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/arb_finder/__init__.py src/arb_finder/calculator.py tests/test_arb_finder_calculator.py
git commit -m "Add arb_finder value-bet edge calculator"
```

---

### Task 3: `arb_finder.finder` orchestration (TDD, real + synthetic data)

**Files:**
- Create: `src/arb_finder/finder.py`
- Test: `tests/test_arb_finder_finder.py`

**Interfaces:**
- Consumes: `polymarket_monitor.models.MoveEvent` (Task 1), `matching.matcher.match_game`/`team_price_for` (already-built), `matching.models.BookmakerGame` (already-built), `notifier.models.ValueBetAlert` (already-built), `calculator.value_bet_edge` (Task 2)
- Produces: `finder.DEFAULT_MIN_EDGE: float = 0.02`, `finder.find_value_bets(move: MoveEvent, paddypower_games: list[BookmakerGame], novibet_games: list[BookmakerGame], min_edge: float = DEFAULT_MIN_EDGE) -> list[ValueBetAlert]`

- [ ] **Step 1: Write the failing tests**

`tests/test_arb_finder_finder.py` — uses the real Commanders/Lions cross-source data (reused from `matching`'s own test suite; both legs are negative-edge in real life, which is itself a meaningful correctness check — a healthy market has more losing bets than winning ones) plus synthetic fixtures for the cases real data doesn't happen to demonstrate (a clearing-the-threshold edge, ranking, one-bookmaker-only matches):

```python
from __future__ import annotations

from datetime import datetime, timezone

from matching.models import BookmakerGame, BookmakerTeamPrice
from notifier.models import ValueBetAlert
from polymarket_monitor.models import MoveEvent

from arb_finder.finder import find_value_bets

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

# Real captured data: Polymarket's Commanders price moved 0.30 -> 0.36
# (a genuine >=5% relative move), matched against the real Paddy Power and
# Novibet games for this exact game (see matching's own test suite).
REAL_MOVE = MoveEvent(
    market_id="m1", question="Commanders vs. Lions", tracked_outcome="Commanders",
    old_price=0.30, new_price=0.36, relative_move=0.20,
    old_at=NOW, new_at=NOW, game_start_time="2026-08-22 16:00:00+00",
)
REAL_PADDYPOWER_GAME = BookmakerGame(
    bookmaker="Paddy Power", event_name="Washington Commanders @ Detroit Lions",
    kickoff_time="2026-08-22T16:00:00.000Z",
    teams=(
        BookmakerTeamPrice(team_name="Washington Commanders", decimal_odds=2.6),
        BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.444444444444444),
    ),
)
REAL_NOVIBET_GAME = BookmakerGame(
    bookmaker="Novibet", event_name="DET Lions vs WAS Commanders",
    kickoff_time="2026-08-22T16:00:00+00:00",
    teams=(
        BookmakerTeamPrice(team_name="DET Lions", decimal_odds=1.42),
        BookmakerTeamPrice(team_name="WAS Commanders", decimal_odds=2.8),
    ),
)

# Synthetic: a game where the bookmaker price genuinely hasn't caught up
# to Polymarket's new fair price — a real positive-edge opportunity.
STALE_MOVE = MoveEvent(
    market_id="m2", question="Bears vs. Lions", tracked_outcome="Bears",
    old_price=0.40, new_price=0.60, relative_move=0.50,
    old_at=NOW, new_at=NOW, game_start_time="2026-11-26 18:00:00+00",
)
STALE_PADDYPOWER_GAME = BookmakerGame(
    bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
    kickoff_time="2026-11-26T18:00:00.000Z",
    teams=(
        # true_prob=0.60; decimal_odds=2.00 -> edge = 2.00*0.60-1 = +0.20
        BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=2.00),
        BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.80),
    ),
)
STALE_NOVIBET_GAME = BookmakerGame(
    bookmaker="Novibet", event_name="DET Lions vs CHI Bears",
    kickoff_time="2026-11-26T18:00:00+00:00",
    teams=(
        BookmakerTeamPrice(team_name="DET Lions", decimal_odds=1.75),
        # true_prob=0.60; decimal_odds=1.90 -> edge = 1.90*0.60-1 = +0.14
        BookmakerTeamPrice(team_name="CHI Bears", decimal_odds=1.90),
    ),
)


def test_real_data_both_legs_below_threshold_returns_empty():
    """Sanity check against genuinely real market data: a healthy,
    roughly-efficient market should NOT produce a value bet here — both
    real bookmaker prices imply a lower Commanders probability than
    Polymarket's, i.e. negative edge, correctly filtered out."""
    alerts = find_value_bets(REAL_MOVE, [REAL_PADDYPOWER_GAME], [REAL_NOVIBET_GAME])
    assert alerts == []


def test_finds_and_ranks_both_legs_when_both_clear_the_threshold():
    alerts = find_value_bets(STALE_MOVE, [STALE_PADDYPOWER_GAME], [STALE_NOVIBET_GAME])

    assert len(alerts) == 2
    assert alerts[0].bookmaker == "Paddy Power"  # +20% edge, ranked first
    assert alerts[1].bookmaker == "Novibet"      # +14% edge, ranked second
    assert round(alerts[0].edge, 6) == 0.20
    assert round(alerts[1].edge, 6) == 0.14


def test_alert_fields_are_populated_correctly():
    alerts = find_value_bets(STALE_MOVE, [STALE_PADDYPOWER_GAME], [])

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert == ValueBetAlert(
        game_name="Bears vs. Lions",
        team_name="Chicago Bears",
        bookmaker="Paddy Power",
        decimal_odds=2.00,
        polymarket_old_price=0.40,
        polymarket_new_price=0.60,
        polymarket_relative_move=0.5,   # SIGNED: (0.60-0.40)/0.40 = +0.5
        edge=0.20,
    )


def test_relative_move_is_negative_when_price_falls():
    falling_move = MoveEvent(
        market_id="m3", question="Bears vs. Lions", tracked_outcome="Bears",
        old_price=0.60, new_price=0.40, relative_move=0.333333333333333,
        old_at=NOW, new_at=NOW, game_start_time="2026-11-26 18:00:00+00",
    )
    # decimal_odds=2.00, true_prob=0.40 -> edge = 2.00*0.40-1 = -0.20 (below threshold)
    # -- but this test only checks the sign is threaded correctly when an
    # edge DOES clear, so use a bookmaker price that still produces a
    # positive edge against the new, lower true_prob.
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=3.00),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=1.50),
        ),
    )
    alerts = find_value_bets(falling_move, [game], [])
    assert len(alerts) == 1
    assert round(alerts[0].polymarket_relative_move, 6) == round((0.40 - 0.60) / 0.60, 6)
    assert alerts[0].polymarket_relative_move < 0


def test_one_bookmaker_with_no_match_does_not_block_the_other():
    unrelated_game = BookmakerGame(
        bookmaker="Novibet", event_name="SEA Seahawks vs ARI Cardinals",
        kickoff_time="2026-11-26T18:00:00+00:00",
        teams=(
            BookmakerTeamPrice(team_name="SEA Seahawks", decimal_odds=1.9),
            BookmakerTeamPrice(team_name="ARI Cardinals", decimal_odds=1.9),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [STALE_PADDYPOWER_GAME], [unrelated_game])
    assert len(alerts) == 1
    assert alerts[0].bookmaker == "Paddy Power"


def test_edge_exactly_at_threshold_is_excluded():
    # The spec's architecture is explicit: "edge > threshold", strictly
    # greater than, not >=. true_prob=0.60, decimal_odds=1.70 -> edge =
    # 1.70*0.60-1 = 0.02 exactly -> excluded.
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=1.70),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=2.00),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [game], [], min_edge=0.02)
    assert alerts == []


def test_edge_just_above_threshold_is_included():
    # true_prob=0.60, decimal_odds=1.71 -> edge = 1.71*0.60-1 = 0.026 (> 0.02)
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=1.71),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=2.00),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [game], [], min_edge=0.02)
    assert len(alerts) == 1


def test_edge_just_below_threshold_is_excluded():
    # true_prob=0.60, decimal_odds=1.69 -> edge = 1.69*0.60-1 = 0.014 (< 0.02)
    game = BookmakerGame(
        bookmaker="Paddy Power", event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        teams=(
            BookmakerTeamPrice(team_name="Chicago Bears", decimal_odds=1.69),
            BookmakerTeamPrice(team_name="Detroit Lions", decimal_odds=2.00),
        ),
    )
    alerts = find_value_bets(STALE_MOVE, [game], [], min_edge=0.02)
    assert alerts == []


def test_no_games_in_either_list_returns_empty():
    assert find_value_bets(STALE_MOVE, [], []) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_arb_finder_finder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'arb_finder.finder'`.

- [ ] **Step 3: Implement `finder.py`**

`src/arb_finder/finder.py`:

```python
"""Join a detected Polymarket move to matched bookmaker prices, compute
the value-bet edge per leg, filter, and rank. See the design spec's
architecture diagram — this is the "-> per matched bookmaker leg: ...
edge = decimal_odds * true_prob - 1" step."""

from __future__ import annotations

from matching.matcher import match_game, team_price_for
from matching.models import BookmakerGame
from notifier.models import ValueBetAlert
from polymarket_monitor.models import MoveEvent

from .calculator import value_bet_edge

DEFAULT_MIN_EDGE = 0.02


def find_value_bets(
    move: MoveEvent,
    paddypower_games: "list[BookmakerGame]",
    novibet_games: "list[BookmakerGame]",
    min_edge: float = DEFAULT_MIN_EDGE,
) -> "list[ValueBetAlert]":
    """Check both bookmakers independently for a value-bet opportunity on
    the moved team. A bookmaker with no match, or an edge not strictly
    greater than `min_edge`, is silently skipped for that leg only —
    never an error, never blocks the other bookmaker. Results are ranked
    by edge descending."""
    alerts: "list[ValueBetAlert]" = []
    for games in (paddypower_games, novibet_games):
        alert = _find_leg(move, games)
        if alert is not None and alert.edge > min_edge:
            alerts.append(alert)
    alerts.sort(key=lambda a: a.edge, reverse=True)
    return alerts


def _find_leg(move: MoveEvent, bookmaker_games: "list[BookmakerGame]") -> "ValueBetAlert | None":
    game = match_game(move.question, move.game_start_time, bookmaker_games)
    if game is None:
        return None
    price = team_price_for(game, move.tracked_outcome)
    if price is None:
        return None

    true_prob = move.new_price
    edge = value_bet_edge(price.decimal_odds, true_prob)
    # MoveEvent.relative_move is an unsigned magnitude (see
    # polymarket_monitor/detector.py) — recompute it signed here, since
    # the notification needs to show direction. Division by move.old_price
    # is safe: MoveDetector guarantees old_price > 0 before ever
    # constructing a MoveEvent.
    signed_relative_move = (move.new_price - move.old_price) / move.old_price

    return ValueBetAlert(
        game_name=move.question,
        team_name=price.team_name,
        bookmaker=game.bookmaker,
        decimal_odds=price.decimal_odds,
        polymarket_old_price=move.old_price,
        polymarket_new_price=move.new_price,
        polymarket_relative_move=signed_relative_move,
        edge=edge,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_arb_finder_finder.py -v`
Expected: PASS — all 9 tests green.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests green, no regressions anywhere in the project.

- [ ] **Step 6: Commit**

```bash
git add src/arb_finder/finder.py tests/test_arb_finder_finder.py
git commit -m "Add arb_finder orchestration: match, price, edge, filter, rank"
```

---

## Self-Review Notes

- **Spec coverage:** `value_bet_edge` matches the spec's formula exactly; the orchestration step matches the spec's architecture diagram's "per matched bookmaker leg: true_prob = Polymarket sell-side price at trigger time; edge = decimal_odds * true_prob - 1" and "edge > threshold (default 2%) AND not in cooldown -> notification" (cooldown is explicitly the `orchestrator`'s job per the spec's module list, not this plan's — `find_value_bets` produces the ranked candidate list the orchestrator will apply cooldown to). `orchestrator` remains out of scope for this plan.
- **Placeholder scan:** no TBDs; every step has complete, runnable code.
- **Type consistency:** `find_value_bets`'s signature and `ValueBetAlert`'s field names are identical between `finder.py` and its tests. `MoveEvent`'s new `game_start_time` field name and default match between Task 1's `models.py`/`detector.py`/`poller.py` changes and Task 3's test fixtures.
- **Critical correctness property called out explicitly:** the signed-vs-unsigned `relative_move` distinction is stated as a Global Constraint, implemented with an inline comment explaining why, and has a dedicated test (`test_relative_move_is_negative_when_price_falls`) — this is exactly the kind of subtle bug (right formula, wrong sign) that would otherwise ship silently and only surface as a confusing notification.
- **Task 1's backward-compatibility requirement is enforced structurally**, not just by convention: Step 1 records a baseline run of the exact files being touched, and Step 2 explicitly instructs appending new tests rather than editing existing ones — a reviewer can directly diff `tests/test_detector.py`/`test_poller.py` against the pre-Task-1 versions to confirm zero unrelated changes.
