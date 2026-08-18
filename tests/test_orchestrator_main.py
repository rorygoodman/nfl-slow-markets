from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import pytest

from orchestrator import main as orchestrator_main
from polymarket_monitor.detector import MoveDetector
from polymarket_monitor.models import MarketSnapshot, MoveEvent


@pytest.fixture(autouse=True)
def _clear_in_flight():
    orchestrator_main._in_flight.clear()
    yield
    orchestrator_main._in_flight.clear()


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

        def poll(self):
            return None  # still running

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


def _make_event(market_id="1", question="Raiders vs. Texans"):
    return MoveEvent(
        market_id=market_id, question=question, tracked_outcome="Raiders",
        old_price=0.50, new_price=0.60, relative_move=0.20,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
    )


class _FakePopen:
    def __init__(self, args, poll_result=None):
        self.args = args
        self._poll_result = poll_result

    def poll(self):
        return self._poll_result


def test_trigger_pipeline_skips_spawn_when_a_run_for_the_market_is_already_in_flight(
    monkeypatch, caplog
):
    spawned = []

    def _popen(args):
        popen = _FakePopen(args, poll_result=None)  # still running
        spawned.append(popen)
        return popen

    monkeypatch.setattr(orchestrator_main.subprocess, "Popen", _popen)

    with caplog.at_level(logging.INFO):
        first = orchestrator_main.trigger_pipeline(_make_event(market_id="1"))
        second = orchestrator_main.trigger_pipeline(_make_event(market_id="1"))

    assert first is not None
    assert second is None
    assert len(spawned) == 1
    assert "already running" in caplog.text


def test_trigger_pipeline_reaps_finished_entry_and_spawns_again(monkeypatch):
    spawned = []

    def _popen(args):
        popen = _FakePopen(args, poll_result=0)  # finished
        spawned.append(popen)
        return popen

    monkeypatch.setattr(orchestrator_main.subprocess, "Popen", _popen)

    first = orchestrator_main.trigger_pipeline(_make_event(market_id="1"))
    second = orchestrator_main.trigger_pipeline(_make_event(market_id="1"))

    assert first is not None
    assert second is not None
    assert len(spawned) == 2


def test_trigger_pipeline_does_not_block_across_different_markets(monkeypatch):
    spawned = []

    def _popen(args):
        popen = _FakePopen(args, poll_result=None)  # still running
        spawned.append(popen)
        return popen

    monkeypatch.setattr(orchestrator_main.subprocess, "Popen", _popen)

    first = orchestrator_main.trigger_pipeline(_make_event(market_id="1"))
    second = orchestrator_main.trigger_pipeline(_make_event(market_id="2"))

    assert first is not None
    assert second is not None
    assert len(spawned) == 2


def test_poll_once_passes_game_start_time_through_to_the_detector(monkeypatch):
    snapshot = MarketSnapshot(
        market_id="1", question="Raiders vs. Texans", tracked_outcome="Raiders",
        best_ask=0.51, game_start_time="2026-08-21 00:00:00+00",
    )
    monkeypatch.setattr(orchestrator_main, "fetch_nfl_moneyline_markets", lambda client: [snapshot])
    detector = _RecordingDetector()

    orchestrator_main.poll_once(client=object(), detector=detector)

    assert detector.calls[0]["game_start_time"] == "2026-08-21 00:00:00+00"
