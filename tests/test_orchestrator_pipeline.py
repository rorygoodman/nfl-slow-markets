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
