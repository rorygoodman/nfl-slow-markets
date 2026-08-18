from __future__ import annotations

from notifier.formatting import format_alert
from notifier.models import ValueBetAlert


def test_formats_title_and_body():
    alert = ValueBetAlert(
        game_name="Raiders vs. Texans",
        team_name="Raiders",
        bookmaker="Paddy Power",
        decimal_odds=2.1,
        polymarket_old_price=0.50,
        polymarket_new_price=0.40,
        polymarket_relative_move=0.20,
        edge=0.05,
    )

    message = format_alert(alert)

    assert message.title == "Raiders value bet: Paddy Power @ 2.10"
    assert message.body == (
        "Raiders vs. Texans\n"
        "Polymarket: 50.0% -> 40.0% (+20.0% relative move)\n"
        "Paddy Power: Raiders @ 2.10 decimal\n"
        "Edge: +5.0%"
    )


def test_formats_a_downward_polymarket_move_without_a_double_negative():
    alert = ValueBetAlert(
        game_name="49ers vs. Chargers",
        team_name="Chargers",
        bookmaker="bet365",
        decimal_odds=1.85,
        polymarket_old_price=0.45,
        polymarket_new_price=0.36,
        polymarket_relative_move=-0.20,
        edge=0.023,
    )

    message = format_alert(alert)

    assert message.title == "Chargers value bet: bet365 @ 1.85"
    assert "45.0% -> 36.0% (-20.0% relative move)" in message.body
    assert "Edge: +2.3%" in message.body
