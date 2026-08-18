from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.serialization import move_event_from_json, move_event_to_json
from polymarket_monitor.models import MoveEvent


def test_round_trip_preserves_all_fields():
    event = MoveEvent(
        market_id="12345",
        question="Commanders vs. Lions",
        tracked_outcome="Commanders",
        old_price=0.55,
        new_price=0.50,
        relative_move=0.0909090909,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
        game_start_time="2026-08-21 00:00:00+00",
    )

    text = move_event_to_json(event)
    result = move_event_from_json(text)

    assert result == event


def test_round_trip_preserves_none_game_start_time():
    event = MoveEvent(
        market_id="1",
        question="Raiders vs. Texans",
        tracked_outcome="Raiders",
        old_price=0.5,
        new_price=0.6,
        relative_move=0.2,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 10, 0, tzinfo=timezone.utc),
        game_start_time=None,
    )

    result = move_event_from_json(move_event_to_json(event))

    assert result.game_start_time is None


def test_to_json_returns_a_string():
    event = MoveEvent(
        market_id="1", question="Q", tracked_outcome="T",
        old_price=0.5, new_price=0.5, relative_move=0.0,
        old_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
        new_at=datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert isinstance(move_event_to_json(event), str)
