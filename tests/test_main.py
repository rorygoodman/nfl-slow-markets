"""Coverage for the real ValueBetAlert -> format_alert -> send_notification
chain, and for notifier.__main__.main()'s wiring (credential-error handling,
exit codes, no-topic-in-stdout)."""

from __future__ import annotations

import json

import httpx
import pytest

import notifier.__main__ as notifier_main
from common.credentials import Credentials
from notifier.formatting import format_alert
from notifier.models import ValueBetAlert
from notifier.ntfy import send_notification


def test_real_alert_composes_through_to_the_wire():
    """Build a real ValueBetAlert, run it through the real format_alert,
    and hand the real NtfyMessage to the real send_notification — proving
    the three pieces wire together correctly, not just in isolation."""
    alert = ValueBetAlert(
        game_name="Raiders vs. Texans",
        team_name="Raiders",
        bookmaker="Paddy Power",
        decimal_odds=2.10,
        polymarket_old_price=0.50,
        polymarket_new_price=0.40,
        polymarket_relative_move=0.20,
        edge=0.05,
    )

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": "abc"})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    message = format_alert(alert)
    ok = send_notification(message, "fake-topic", client=client)

    assert ok is True
    assert captured["json"] == {
        "topic": "fake-topic",
        "title": "Raiders value bet: Paddy Power @ 2.10",
        "message": (
            "Raiders vs. Texans\n"
            "Polymarket: 50.0% -> 40.0% (+20.0% relative move)\n"
            "Paddy Power: Raiders @ 2.10 decimal\n"
            "Edge: +5.0%"
        ),
    }


def test_main_returns_0_and_stdout_names_no_topic(monkeypatch, capsys):
    monkeypatch.setattr(
        notifier_main,
        "load_credentials",
        lambda path: Credentials(ntfy_topic="fake-topic"),
    )
    monkeypatch.setattr(notifier_main, "send_notification", lambda message, topic: True)

    exit_code = notifier_main.main()

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "fake-topic" not in out
    assert out == "Sent test notification.\n"


def test_main_returns_1_and_logs_no_topic_when_credentials_invalid(monkeypatch, capsys):
    def raise_bad_creds(path):
        raise ValueError("credentials JSON missing or non-string field: ntfy_topic")

    monkeypatch.setattr(notifier_main, "load_credentials", raise_bad_creds)

    exit_code = notifier_main.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "ntfy_topic" in captured.err
    assert captured.out == ""


def test_main_returns_1_and_stderr_names_no_topic_when_send_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        notifier_main,
        "load_credentials",
        lambda path: Credentials(ntfy_topic="fake-topic"),
    )
    monkeypatch.setattr(notifier_main, "send_notification", lambda message, topic: False)

    exit_code = notifier_main.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "fake-topic" not in captured.err
    assert "fake-topic" not in captured.out
