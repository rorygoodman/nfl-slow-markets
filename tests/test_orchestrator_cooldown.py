from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.cooldown import (
    is_in_cooldown,
    load_cooldowns,
    record_alert,
    save_cooldowns,
)

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def test_is_in_cooldown_false_when_key_absent():
    assert is_in_cooldown({}, "market-1", "Paddy Power", NOW) is False


def test_is_in_cooldown_true_within_window():
    cooldowns = {"market-1|Paddy Power": (NOW - timedelta(minutes=10)).isoformat()}
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is True


def test_is_in_cooldown_false_outside_window():
    cooldowns = {"market-1|Paddy Power": (NOW - timedelta(minutes=31)).isoformat()}
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is False


def test_is_in_cooldown_respects_custom_window():
    cooldowns = {"market-1|Paddy Power": (NOW - timedelta(minutes=5)).isoformat()}
    assert (
        is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW, window=timedelta(minutes=1))
        is False
    )


def test_is_in_cooldown_false_on_malformed_timestamp():
    cooldowns = {"market-1|Paddy Power": "not-a-timestamp"}
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is False


def test_is_in_cooldown_distinguishes_bookmakers():
    cooldowns = {"market-1|Paddy Power": NOW.isoformat()}
    assert is_in_cooldown(cooldowns, "market-1", "Novibet", NOW) is False


def test_is_in_cooldown_distinguishes_markets():
    cooldowns = {"market-1|Paddy Power": NOW.isoformat()}
    assert is_in_cooldown(cooldowns, "market-2", "Paddy Power", NOW) is False


def test_record_alert_then_is_in_cooldown_round_trips_true():
    cooldowns: dict[str, str] = {}
    record_alert(cooldowns, "market-1", "Paddy Power", NOW)
    assert is_in_cooldown(cooldowns, "market-1", "Paddy Power", NOW) is True


def test_load_cooldowns_missing_file_returns_empty_dict(tmp_path):
    path = tmp_path / "cooldown.json"
    assert load_cooldowns(path) == {}


def test_load_cooldowns_corrupt_json_returns_empty_dict(tmp_path):
    path = tmp_path / "cooldown.json"
    path.write_text("{not valid json")
    assert load_cooldowns(path) == {}


def test_load_cooldowns_non_object_json_returns_empty_dict(tmp_path):
    path = tmp_path / "cooldown.json"
    path.write_text("[1, 2, 3]")
    assert load_cooldowns(path) == {}


def test_save_then_load_round_trips_and_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "cooldown.json"
    cooldowns = {"market-1|Paddy Power": NOW.isoformat()}

    save_cooldowns(path, cooldowns)
    result = load_cooldowns(path)

    assert result == cooldowns


def test_save_cooldowns_fails_open_on_os_error(tmp_path, capsys):
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("")
    path = blocker / "cooldown.json"  # blocker is a file, not a dir -> mkdir(parents=True) raises

    save_cooldowns(path, {"market-1|Paddy Power": "2026-08-18T12:00:00+00:00"})

    assert "failed to save cooldown file" in capsys.readouterr().err
