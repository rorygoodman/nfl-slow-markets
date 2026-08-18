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
            f"{NTFY_BASE_URL}/",
            json={"topic": topic, "title": message.title, "message": message.body},
        )
        if response.status_code // 100 != 2:
            print(f"notifier: ntfy returned HTTP {response.status_code}", file=sys.stderr)
            return False
        return True
    except Exception as exc:
        # Broad by design: this function's whole contract is "send a
        # best-effort notification, never let a failure here propagate."
        # httpx's json= publish (unlike the old header-based API) handles
        # UTF-8 titles/bodies and keeps the topic out of the URL entirely,
        # but network errors (httpx.HTTPError subclasses) and other
        # unexpected failures can still surface here, so keep this broad.
        print(f"notifier: failed to send ntfy notification: {exc}", file=sys.stderr)
        return False
    finally:
        if owns_client:
            http.close()
