from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polymarket_monitor.detector import MoveDetector

T0 = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_no_trigger_without_ten_minutes_of_history():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    # A huge jump 5 minutes later, but we don't have 10 minutes of history yet.
    event = detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.90, T0 + timedelta(minutes=5))
    assert event is None


def test_triggers_at_exactly_five_percent_relative_move_up():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.525, T0 + timedelta(minutes=10)
    )
    assert event is not None
    assert event.old_price == 0.50
    assert event.new_price == 0.525
    assert round(event.relative_move, 6) == 0.05


def test_no_trigger_below_five_percent_relative_move():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.524, T0 + timedelta(minutes=10)
    )
    assert event is None


def test_triggers_on_downward_move():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.40, T0 + timedelta(minutes=10)
    )
    assert event is not None
    assert event.old_price == 0.50
    assert event.new_price == 0.40
    assert round(event.relative_move, 6) == 0.20


def test_reference_is_oldest_sample_still_inside_trailing_window():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.51, T0 + timedelta(minutes=3))
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.52, T0 + timedelta(minutes=6))
    # At T0+11min, the T0 sample (11 min old) has aged out of the 10-min
    # window; the reference should be the T0+3min sample (8 min old), not T0.
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.60, T0 + timedelta(minutes=11)
    )
    assert event is not None
    assert event.old_price == 0.51


def test_gap_exceeding_window_prunes_stale_reference_and_does_not_trigger():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    # Gap longer than the 10-minute window: the old sample ages out before
    # this poll arrives, so there's no valid "10 minutes ago" reference.
    event = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.80, T0 + timedelta(minutes=25)
    )
    assert event is None


def test_markets_are_tracked_independently():
    detector = MoveDetector()
    detector.observe("m1", "Raiders vs. Texans", "Raiders", 0.50, T0)
    detector.observe("m2", "49ers vs. Chargers", "49ers", 0.50, T0)
    event_m2 = detector.observe(
        "m2", "49ers vs. Chargers", "49ers", 0.80, T0 + timedelta(minutes=10)
    )
    event_m1 = detector.observe(
        "m1", "Raiders vs. Texans", "Raiders", 0.50, T0 + timedelta(minutes=10)
    )
    assert event_m2 is not None
    assert event_m1 is None
