from __future__ import annotations

import sys

import httpx

from .models import NtfyMessage

NTFY_BASE_URL = "https://ntfy.sh"


def send_notification(
    message: NtfyMessage, topic: str, client: httpx.Client | None = None
) -> bool:
    """POST message to the given ntfy topic. Never raises — returns True on
    a 2xx response, False (logged to stderr) on any failure."""
    owns_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        response = http.post(
            f"{NTFY_BASE_URL}/{topic}",
            content=message.body.encode("utf-8"),
            headers={"Title": message.title},
        )
        if response.status_code // 100 != 2:
            print(f"notifier: ntfy returned HTTP {response.status_code}", file=sys.stderr)
            return False
        return True
    except httpx.HTTPError as exc:
        print(f"notifier: failed to send ntfy notification: {exc}", file=sys.stderr)
        return False
    finally:
        if owns_client:
            http.close()
