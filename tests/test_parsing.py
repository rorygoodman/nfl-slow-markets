from __future__ import annotations

from paddypower_scraper.models import NFLGameOdds, TeamPrice
from paddypower_scraper.parsing import parse_competition_page


def test_parses_the_one_valid_open_moneyline_market(competition_page_payload):
    games = parse_competition_page(competition_page_payload)
    assert len(games) == 1
    game = games[0]
    assert game == NFLGameOdds(
        market_id="927.383543353",
        event_id="35607159",
        event_name="Chicago Bears @ Detroit Lions",
        kickoff_time="2026-11-26T18:00:00.000Z",
        competition_id=12282733,
        teams=(
            TeamPrice(team_name="Chicago Bears", selection_id=50194,
                      decimal_odds=2.1, home_or_away="AWAY"),
            TeamPrice(team_name="Detroit Lions", selection_id=50193,
                      decimal_odds=1.727272727272727, home_or_away="HOME"),
        ),
    )


def test_skips_non_moneyline_markets(competition_page_payload):
    games = parse_competition_page(competition_page_payload)
    assert all(g.market_id != "927.900000001" for g in games)


def test_skips_suspended_moneyline_markets(competition_page_payload):
    games = parse_competition_page(competition_page_payload)
    assert all(g.market_id != "927.900000002" for g in games)


def test_returns_empty_list_for_no_markets():
    assert parse_competition_page({"attachments": {"events": {}, "markets": {}}}) == []


def test_skips_market_with_missing_event():
    raw = {
        "attachments": {
            "events": {},
            "markets": {
                "927.1": {
                    "marketId": "927.1", "eventId": 999, "competitionId": 1,
                    "marketType": "MONEY_LINE", "marketStatus": "OPEN",
                    "numberOfRunners": 2,
                    "runners": [
                        {"selectionId": 1, "runnerName": "A", "result": {"type": "AWAY"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 2.0}}}},
                        {"selectionId": 2, "runnerName": "B", "result": {"type": "HOME"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}},
                    ],
                }
            },
        }
    }
    assert parse_competition_page(raw) == []


def test_skips_runner_missing_odds():
    raw = {
        "attachments": {
            "events": {"1": {"eventId": 1, "name": "A @ B", "openDate": "2026-01-01T00:00:00.000Z"}},
            "markets": {
                "927.1": {
                    "marketId": "927.1", "eventId": 1, "competitionId": 1,
                    "marketType": "MONEY_LINE", "marketStatus": "OPEN",
                    "numberOfRunners": 2,
                    "runners": [
                        {"selectionId": 1, "runnerName": "A", "result": {"type": "AWAY"},
                         "runnerStatus": "ACTIVE", "winRunnerOdds": {}},
                        {"selectionId": 2, "runnerName": "B", "result": {"type": "HOME"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}},
                    ],
                }
            },
        }
    }
    assert parse_competition_page(raw) == []


def test_skips_runner_with_inactive_status():
    raw = {
        "attachments": {
            "events": {"1": {"eventId": 1, "name": "A @ B", "openDate": "2026-01-01T00:00:00.000Z"}},
            "markets": {
                "927.1": {
                    "marketId": "927.1", "eventId": 1, "competitionId": 1,
                    "marketType": "MONEY_LINE", "marketStatus": "OPEN",
                    "numberOfRunners": 2,
                    "runners": [
                        {"selectionId": 1, "runnerName": "A", "result": {"type": "AWAY"},
                         "runnerStatus": "SUSPENDED",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 2.0}}}},
                        {"selectionId": 2, "runnerName": "B", "result": {"type": "HOME"},
                         "runnerStatus": "ACTIVE",
                         "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.9}}}},
                    ],
                }
            },
        }
    }
    assert parse_competition_page(raw) == []
