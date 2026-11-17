"""Unit tests for multi-season historical race database (2021-2026)."""

from __future__ import annotations

from stratos.data.historical_db import (
    HISTORICAL_RACES,
    get_available_seasons,
    get_multi_season_strategy_distribution,
    get_race_stats,
    get_races_for_season,
)


def test_seasons_range_includes_2026() -> None:
    """Ensure database covers seasons from 2021 through 2026 inclusive."""
    seasons = get_available_seasons()
    assert 2026 in seasons
    assert 2021 in seasons
    assert len(seasons) >= 6


def test_2026_races_populated() -> None:
    """Ensure 2026 season contains valid race records."""
    races_2026 = get_races_for_season(2026)
    assert len(races_2026) >= 4
    bahrain = next(r for r in races_2026 if "Bahrain" in r.race_name)
    assert bahrain.season == 2026
    assert bahrain.winner_driver in ["NOR", "VER", "LEC", "HAM", "PIA"]
    assert bahrain.total_pit_stops > 0
    assert bahrain.avg_track_temp > 20.0


def test_get_race_stats_query() -> None:
    """Test lookup of specific race by season and name substring."""
    race = get_race_stats(2024, "Bahrain")
    assert race is not None
    assert race.season == 2024
    assert race.winner_driver == "VER"
    assert "Sakhir" in race.circuit_name

    non_existent = get_race_stats(2024, "Atlantis")
    assert non_existent is None


def test_multi_season_strategy_distribution() -> None:
    """Verify aggregated strategy distribution across all seasons."""
    dist = get_multi_season_strategy_distribution()
    assert len(dist) == len(get_available_seasons())
    for item in dist:
        assert "season" in item
        assert "1_stop" in item
        assert "2_stop" in item
        assert "3_plus_stop" in item
        assert item["total_races"] > 0
        assert item["1_stop"] + item["2_stop"] + item["3_plus_stop"] == item["total_races"]


def test_all_historical_records_have_valid_fields() -> None:
    """Verify data integrity across all historical race entries."""
    for r in HISTORICAL_RACES:
        assert 2021 <= r.season <= 2026
        assert r.round_num >= 1
        assert len(r.country_flag) > 0
        assert len(r.winner_driver) >= 3
        assert len(r.winning_strategy) > 0
        assert r.total_pit_stops > 0
        assert 0.0 <= r.undercut_success_rate <= 1.0
        assert r.avg_pit_loss > 15.0
        assert len(r.event_date) == 10
        assert r.event_date.startswith(str(r.season))
