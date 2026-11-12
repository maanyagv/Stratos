"""Unit tests for Alpine and Formula 1 performance metrics calculations."""

from __future__ import annotations

import pandas as pd
import pytest

from stratos.alpine.metrics import (
    calculate_clean_lap_pace,
    calculate_normalized_pace,
    calculate_pit_performance,
    calculate_qualifying_performance,
    calculate_reliability_stats,
    calculate_sector_performance,
    calculate_speed_trap_performance,
    calculate_teammate_comparison,
    calculate_tyre_degradation,
)


@pytest.fixture
def sample_laps() -> pd.DataFrame:
    """Provide realistic sample lap records for telemetry tests."""
    return pd.DataFrame(
        {
            "driver": ["GAS", "GAS", "GAS", "OCO", "OCO", "OCO", "VER", "VER"],
            "team": [
                "Alpine",
                "Alpine",
                "Alpine",
                "Alpine",
                "Alpine",
                "Alpine",
                "Red Bull",
                "Red Bull",
            ],
            "lap_number": [1, 2, 3, 1, 2, 3, 1, 2],
            "lap_time_seconds": [92.0, 92.4, 92.8, 92.2, 92.5, 93.0, 90.0, 90.2],
            "sector_1_seconds": [28.5, 28.6, 28.7, 28.6, 28.7, 28.8, 28.0, 28.1],
            "sector_2_seconds": [38.5, 38.6, 38.7, 38.5, 38.6, 38.8, 37.5, 37.6],
            "sector_3_seconds": [25.0, 25.2, 25.4, 25.1, 25.2, 25.4, 24.5, 24.5],
            "speed_st": [325.0, 326.5, 324.0, 324.5, 325.0, 323.5, 332.0, 333.5],
            "speed_fl": [295.0, 296.0, 294.5, 295.0, 295.5, 294.0, 302.0, 303.0],
            "speed_i1": [310.0, 311.0, 309.5, 310.0, 310.5, 309.0, 315.0, 316.0],
            "speed_i2": [280.0, 281.0, 279.5, 280.0, 280.5, 279.0, 288.0, 289.0],
            "compound": ["MEDIUM"] * 8,
            "tyre_life": [1, 2, 3, 1, 2, 3, 1, 2],
            "is_clean_lap": [True] * 8,
        }
    )


def test_clean_lap_pace_calculation(sample_laps: pd.DataFrame) -> None:
    """Verify clean-lap pace median, spread, and delta to field median."""
    res = calculate_clean_lap_pace(sample_laps)
    assert res["field_median"] is not None
    assert "GAS" in res["drivers"]
    assert "VER" in res["drivers"]
    assert res["drivers"]["GAS"]["median_pace"] == 92.4
    assert res["drivers"]["VER"]["median_pace"] == 90.1
    # Max Verstappen is faster than field median (negative delta)
    assert res["drivers"]["VER"]["delta_to_field_median"] < 0
    # Pierre Gasly is slower than field median (positive delta)
    assert res["drivers"]["GAS"]["delta_to_field_median"] > 0


def test_normalized_pace_percentage(sample_laps: pd.DataFrame) -> None:
    """Verify lap time normalization relative to field median."""
    norm_df = calculate_normalized_pace(sample_laps, reference_method="field_median")
    assert "normalized_pace_delta_pct" in norm_df.columns
    # VER lap 1 (90.0s) should have negative percentage delta (faster than median ~92.3s)
    ver_lap1_pct = norm_df.loc[
        (norm_df["driver"] == "VER") & (norm_df["lap_number"] == 1),
        "normalized_pace_delta_pct",
    ].values[0]
    assert ver_lap1_pct < 0.0


def test_sector_performance(sample_laps: pd.DataFrame) -> None:
    """Verify sector median calculations."""
    sectors = calculate_sector_performance(sample_laps)
    assert "Alpine" in sectors
    assert "Red Bull" in sectors
    assert sectors["Alpine"]["sector_1_median"] > 0
    assert sectors["Alpine"]["sector_2_median"] > 0
    assert sectors["Alpine"]["sector_3_median"] > 0
    assert sectors["Red Bull"]["sector_1_median"] < sectors["Alpine"]["sector_1_median"]


def test_speed_trap_performance(sample_laps: pd.DataFrame) -> None:
    """Verify speed trap maximums and medians."""
    speeds = calculate_speed_trap_performance(sample_laps)
    assert "Alpine" in speeds
    assert "Red Bull" in speeds
    assert speeds["Red Bull"]["speed_st_max"] >= 333.5
    assert speeds["Alpine"]["speed_st_max"] >= 326.5


def test_qualifying_performance_deltas() -> None:
    """Verify qualifying pole delta computation."""
    qualy_results = [
        {
            "driver_code": "VER",
            "driver_name": "Max Verstappen",
            "constructor_id": "red_bull",
            "q3_time": 88.5,
            "grid_position": 1,
        },
        {
            "driver_code": "GAS",
            "driver_name": "Pierre Gasly",
            "constructor_id": "alpine",
            "q2_time": 89.8,
            "grid_position": 10,
        },
        {
            "driver_code": "OCO",
            "driver_name": "Esteban Ocon",
            "constructor_id": "alpine",
            "q2_time": 90.0,
            "grid_position": 12,
        },
    ]

    res = calculate_qualifying_performance(qualy_results)
    assert res["pole_time"] == 88.5
    assert res["drivers"]["VER"]["delta_seconds"] == 0.0
    assert res["drivers"]["GAS"]["delta_seconds"] == 1.3
    assert res["drivers"]["GAS"]["delta_pct"] > 0
    assert "alpine" in res["constructors"]


def test_teammate_comparison(sample_laps: pd.DataFrame) -> None:
    """Verify intra-team teammate pace and qualifying delta."""
    results = [
        {
            "driver_code": "GAS",
            "driver_name": "Pierre Gasly",
            "constructor_id": "alpine",
            "finish_position": 9,
            "points": 2.0,
            "fastest_lap_time": 92.0,
        },
        {
            "driver_code": "OCO",
            "driver_name": "Esteban Ocon",
            "constructor_id": "alpine",
            "finish_position": 10,
            "points": 1.0,
            "fastest_lap_time": 92.2,
        },
    ]

    comp = calculate_teammate_comparison(sample_laps, results, constructor_id="alpine")
    assert comp["driver_1"] == "GAS"
    assert comp["driver_2"] == "OCO"
    assert comp["finish_position_delta"] == -1  # GAS finished 1 place ahead
    assert comp["points_delta"] == 1.0  # GAS scored 1 more point


def test_tyre_degradation_slopes() -> None:
    """Verify linear regression of fuel-corrected pace against tyre age."""
    # Synthetic 15-lap stint with 0.08 s/lap true degradation
    laps = []
    for life in range(1, 16):
        # lap time increases by 0.08s per lap of age, minus 0.033s fuel burn
        lap_time = 90.0 + (life * 0.08) - (life * 0.033)
        laps.append(
            {
                "lap_number": life,
                "tyre_life": life,
                "lap_time_seconds": lap_time,
                "compound": "HARD",
                "is_clean_lap": True,
            }
        )
    df = pd.DataFrame(laps)

    deg = calculate_tyre_degradation(df, fuel_correction_per_lap=0.033)
    assert "HARD" in deg
    slope = deg["HARD"]["degradation_rate_sec_per_lap"]
    # Should recover ~0.08 s/lap true degradation
    assert pytest.approx(slope, abs=0.01) == 0.08
    assert deg["HARD"]["r_squared"] > 0.95


def test_pit_performance() -> None:
    """Verify stationary pit duration and pit lane transit losses."""
    stops = [
        {"pit_duration": 2.4, "pit_lane_time": 21.5},
        {"pit_duration": 2.6, "pit_lane_time": 21.8},
        {"pit_duration": 3.1, "pit_lane_time": 22.3},
    ]
    perf = calculate_pit_performance(stops)
    assert perf["total_stops"] == 3
    assert perf["stationary_median"] == 2.6
    assert perf["stationary_min"] == 2.4
    assert perf["pit_lane_loss_median"] == 21.8


def test_reliability_stats() -> None:
    """Verify classified rate %, mechanical DNFs, and points calculation."""
    results = pd.DataFrame(
        {
            "constructor_id": ["alpine", "alpine", "alpine", "alpine", "alpine"],
            "finish_status": ["Finished", "+1 Lap", "Engine", "Collision", "Finished"],
            "points": [10.0, 4.0, 0.0, 0.0, 6.0],
        }
    )
    rel = calculate_reliability_stats(results, constructor_id="alpine")
    assert rel["total_starts"] == 5
    assert rel["classified_finishes"] == 3  # Finished, +1 Lap, Finished
    assert rel["classified_rate_pct"] == 60.0
    assert rel["mechanical_dnfs"] == 1  # Engine
    assert rel["collision_dnfs"] == 1  # Collision
    assert rel["total_points"] == 20.0
    assert rel["points_per_start"] == 4.0
