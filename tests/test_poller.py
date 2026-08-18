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
