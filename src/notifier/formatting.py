from __future__ import annotations

from .models import NtfyMessage, ValueBetAlert


def format_alert(alert: ValueBetAlert) -> NtfyMessage:
    title = f"{alert.team_name} value bet: {alert.bookmaker} @ {alert.decimal_odds:.2f}"
    body = (
        f"{alert.game_name}\n"
        f"Polymarket: {alert.polymarket_old_price:.1%} -> "
        f"{alert.polymarket_new_price:.1%} "
        f"({alert.polymarket_relative_move:+.1%} relative move)\n"
        f"{alert.bookmaker}: {alert.team_name} @ {alert.decimal_odds:.2f} decimal\n"
        f"Edge: {alert.edge:+.1%}"
    )
    return NtfyMessage(title=title, body=body)
