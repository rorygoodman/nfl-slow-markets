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
    except Exception as exc:
        # Broad by design: this function's whole contract is "send a
        # best-effort notification, never let a failure here propagate."
        # httpx.Client.post()/build_request() can raise things that are NOT
        # httpx.HTTPError subclasses — e.g. httpx.InvalidURL (a plain
        # Exception subclass) for a topic containing a non-printable ASCII
        # character, or UnicodeEncodeError (a builtin) for a non-ASCII
        # message title — and those must be caught here too.
        print(f"notifier: failed to send ntfy notification: {exc}", file=sys.stderr)
        return False
    finally:
        if owns_client:
            http.close()
