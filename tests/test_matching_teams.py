from __future__ import annotations

from matching.teams import normalize_team_nickname


def test_normalizes_a_bare_nickname():
    assert normalize_team_nickname("Raiders") == "raiders"


def test_normalizes_a_full_city_and_nickname():
    assert normalize_team_nickname("Las Vegas Raiders") == "raiders"


def test_normalizes_an_abbreviated_city_and_nickname():
    assert normalize_team_nickname("LV Raiders") == "raiders"


def test_normalizes_a_nickname_starting_with_a_digit():
    assert normalize_team_nickname("San Francisco 49ers") == "49ers"
    assert normalize_team_nickname("SF 49ers") == "49ers"
    assert normalize_team_nickname("49ers") == "49ers"


def test_is_case_insensitive():
    assert normalize_team_nickname("RAIDERS") == "raiders"
    assert normalize_team_nickname("raiders") == "raiders"


def test_returns_none_for_an_unrecognized_last_token():
    assert normalize_team_nickname("Some Nonexistent Team") is None


def test_returns_none_for_empty_or_non_string_input():
    assert normalize_team_nickname("") is None
    assert normalize_team_nickname("   ") is None
    assert normalize_team_nickname(None) is None


def test_all_32_current_nfl_nicknames_are_recognized():
    nicknames = [
        "Cardinals", "Falcons", "Ravens", "Bills", "Panthers", "Bears",
        "Bengals", "Browns", "Cowboys", "Broncos", "Lions", "Packers",
        "Texans", "Colts", "Jaguars", "Chiefs", "Raiders", "Chargers",
        "Rams", "Dolphins", "Vikings", "Patriots", "Saints", "Giants",
        "Jets", "Eagles", "Steelers", "49ers", "Seahawks", "Buccaneers",
        "Titans", "Commanders",
    ]
    assert len(nicknames) == 32
    for nickname in nicknames:
        assert normalize_team_nickname(nickname) == nickname.lower()
