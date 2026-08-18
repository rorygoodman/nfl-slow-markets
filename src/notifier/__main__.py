from __future__ import annotations

import sys

from common.credentials import default_credentials_path, load_credentials
from .formatting import format_alert
from .models import ValueBetAlert
from .ntfy import send_notification

_TEST_ALERT = ValueBetAlert(
    game_name="[TEST] Raiders vs. Texans",
    team_name="Raiders",
    bookmaker="Paddy Power",
    decimal_odds=2.00,
    polymarket_old_price=0.50,
    polymarket_new_price=0.525,
    polymarket_relative_move=0.05,
    edge=0.05,
)


def main() -> int:
    try:
        creds = load_credentials(default_credentials_path())
    except ValueError as exc:
        print(f"notifier: {exc}", file=sys.stderr)
        return 1

    message = format_alert(_TEST_ALERT)
    ok = send_notification(message, creds.ntfy_topic)
    if not ok:
        print("Failed to send test notification", file=sys.stderr)
        return 1
    print("Sent test notification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
