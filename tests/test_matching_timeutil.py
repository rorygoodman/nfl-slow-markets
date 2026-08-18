from __future__ import annotations

from datetime import datetime, timezone

from matching.timeutil import to_instant

EXPECTED = datetime(2026, 8, 22, 16, 0, 0, tzinfo=timezone.utc)


def test_parses_polymarket_format():
    assert to_instant("2026-08-22 16:00:00+00") == EXPECTED


def test_parses_paddypower_format():
    assert to_instant("2026-08-22T16:00:00.000Z") == EXPECTED


def test_parses_novibet_format():
    assert to_instant("2026-08-22T16:00:00+00:00") == EXPECTED


def test_returns_none_for_unparseable_string():
    assert to_instant("not a timestamp") is None


def test_returns_none_for_none_input():
    assert to_instant(None) is None


def test_returns_none_for_empty_string():
    assert to_instant("") is None


def test_assumes_utc_when_timestamp_has_no_offset():
    assert to_instant("2026-08-22T16:00:00") == EXPECTED
