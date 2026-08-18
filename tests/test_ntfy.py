from __future__ import annotations

import json

import httpx

from notifier.models import NtfyMessage
from notifier.ntfy import send_notification


def test_sends_post_with_json_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": "abc"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    message = NtfyMessage(title="Test Title", body="Test body")

    ok = send_notification(message, "my-topic", client=client)

    assert ok is True
    assert captured["url"] == "https://ntfy.sh/"
    assert captured["json"] == {
        "topic": "my-topic",
        "title": "Test Title",
        "message": "Test body",
    }


def test_returns_false_on_non_2xx(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    ok = send_notification(NtfyMessage(title="t", body="b"), "topic", client=client)

    assert ok is False
    assert "500" in capsys.readouterr().err


def test_returns_false_on_network_error(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    ok = send_notification(NtfyMessage(title="t", body="b"), "topic", client=client)

    assert ok is False
    assert "notifier" in capsys.readouterr().err


def test_sends_non_ascii_title_successfully():
    # Prior to the JSON-endpoint switch this used the header-based API,
    # where a non-ASCII Title header raised UnicodeEncodeError and the
    # notification was silently dropped. The JSON body handles UTF-8
    # natively, so this must now succeed.
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": "abc"})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    ok = send_notification(
        NtfyMessage(title="Café Bet Alert", body="b"), "topic", client=client
    )

    assert ok is True
    assert captured["json"]["title"] == "Café Bet Alert"
