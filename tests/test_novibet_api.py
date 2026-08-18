from __future__ import annotations

from novibet_scraper.api import (
    NFL_MARKET_VIEW_GROUP_ID,
    NFL_PRESEASON_MARKET_VIEW_GROUP_ID,
    location_feed_url,
)


def test_nfl_preseason_market_view_group_id_is_correct():
    assert NFL_PRESEASON_MARKET_VIEW_GROUP_ID == 5813718


def test_nfl_regular_season_market_view_group_id_is_correct():
    assert NFL_MARKET_VIEW_GROUP_ID == 4799943


def test_location_feed_url_includes_the_group_id_and_fixed_params():
    url = location_feed_url(5813718, timestamp_ms=1234567890)
    assert url == (
        "https://www.novibet.ie/spt/feed/marketviews/location/v2/4324/5813718/"
        "?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE&timestamp=1234567890"
    )


def test_location_feed_url_differs_by_group_id():
    a = location_feed_url(5813718, timestamp_ms=1)
    b = location_feed_url(4799943, timestamp_ms=1)
    assert a != b


def test_location_feed_url_generates_a_timestamp_when_not_given():
    url = location_feed_url(5813718)
    assert "timestamp=" in url
