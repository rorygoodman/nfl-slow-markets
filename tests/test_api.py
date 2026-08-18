from __future__ import annotations

from paddypower_scraper.api import (
    NFL_COMPETITION_ID,
    NFL_PRESEASON_COMPETITION_ID,
    competition_page_url,
)


def test_nfl_preseason_competition_id_is_correct():
    assert NFL_PRESEASON_COMPETITION_ID == 11432305


def test_nfl_regular_season_competition_id_is_correct():
    assert NFL_COMPETITION_ID == 12282733


def test_competition_page_url_includes_the_competition_id():
    url = competition_page_url(11432305)
    assert url.startswith("https://apisms.paddypower.com/smspp/competition-page/v3?")
    assert "competitionId=11432305" in url
    assert "eventTypeId=6423" in url


def test_competition_page_url_differs_by_competition_id():
    assert competition_page_url(1) != competition_page_url(2)
