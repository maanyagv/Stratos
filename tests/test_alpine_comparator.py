"""Unit tests for AlpinePerformanceComparator high-level comparative benchmarking."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from stratos.alpine.comparator import AlpinePerformanceComparator
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore


@pytest.fixture
def populated_env() -> tuple[StratosDB, ParquetStore, Path]:
    """Provide an isolated environment with sample historical session data."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t_path = Path(tmp)
        db = StratosDB(db_path=t_path / "stratos.db")
        store = ParquetStore(root_dir=t_path / "processed")

        # 1. Add Event
        db.upsert_event(
            {
                "id": "2024_01_BAH",
                "season": 2024,
                "round_number": 1,
                "event_name": "Bahrain Grand Prix",
            }
        )

        # 2. Add Session
        db.upsert_session(
            {
                "id": "2024_01_R",
                "event_id": "2024_01_BAH",
                "season": 2024,
                "round_number": 1,
                "session_type": "R",
                "session_name": "Bahrain Grand Prix Race",
            }
        )

        # 3. Add Results across constructors
        results = [
            {
                "driver_code": "VER",
                "driver_name": "Max Verstappen",
                "constructor_id": "red_bull",
                "constructor_name": "Oracle Red Bull Racing",
                "finish_position": 1,
                "points": 26.0,
                "finish_status": "Finished",
            },
            {
                "driver_code": "NOR",
                "driver_name": "Lando Norris",
                "constructor_id": "mclaren",
                "constructor_name": "McLaren Formula 1 Team",
                "finish_position": 6,
                "points": 8.0,
                "finish_status": "Finished",
            },
            {
                "driver_code": "HUL",
                "driver_name": "Nico Hülkenberg",
                "constructor_id": "haas",
                "constructor_name": "MoneyGram Haas F1 Team",
                "finish_position": 10,
                "points": 1.0,
                "finish_status": "Finished",
            },
            {
                "driver_code": "GAS",
                "driver_name": "Pierre Gasly",
                "constructor_id": "alpine",
                "constructor_name": "BWT Alpine F1 Team",
                "finish_position": 11,
                "points": 0.0,
                "finish_status": "Finished",
            },
            {
                "driver_code": "OCO",
                "driver_name": "Esteban Ocon",
                "constructor_id": "alpine",
                "constructor_name": "BWT Alpine F1 Team",
                "finish_position": 12,
                "points": 0.0,
                "finish_status": "Finished",
            },
        ]
        db.save_session_results("2024_01_R", results)

        # 4. Save processed laps
        laps_df = pd.DataFrame(
            {
                "driver": ["VER", "VER", "NOR", "NOR", "HUL", "HUL", "GAS", "GAS", "OCO", "OCO"],
                "team": [
                    "Red Bull",
                    "Red Bull",
                    "McLaren",
                    "McLaren",
                    "Haas",
                    "Haas",
                    "Alpine",
                    "Alpine",
                    "Alpine",
                    "Alpine",
                ],
                "lap_number": [1, 2] * 5,
                "lap_time_seconds": [
                    90.0,
                    90.2,  # Red Bull ~90.1
                    91.0,
                    91.2,  # McLaren ~91.1
                    92.0,
                    92.2,  # Haas ~92.1
                    92.4,
                    92.6,  # Alpine Gasly ~92.5
                    92.5,
                    92.7,  # Alpine Ocon ~92.6
                ],
                "is_clean_lap": [True] * 10,
            }
        )
        store.save_laps(2024, 1, "R", laps_df)

        yield db, store, t_path


def test_compare_vs_field(populated_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify field hierarchy ranking and Alpine position."""
    db, store, _ = populated_env
    comparator = AlpinePerformanceComparator(db=db, parquet_store=store)

    comp = comparator.compare_vs_field(season=2024, round_number=1, session_type="R")
    assert comp["total_teams_measured"] == 4
    # Fastest to slowest: Red Bull (1), McLaren (2), Haas (3), Alpine (4)
    assert comp["alpine_rank"] == 4
    assert comp["alpine_pace"] is not None
    assert comp["alpine_pace"]["median_pace"] == pytest.approx(92.55, abs=0.1)


def test_compare_vs_rivals(populated_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify filtering against dynamic season rivals."""
    db, store, _ = populated_env
    comparator = AlpinePerformanceComparator(db=db, parquet_store=store)

    comp = comparator.compare_vs_rivals(
        season=2024, round_number=1, session_type="R", rivals=["haas"]
    )
    teams = [t["team"] for t in comp["comparison"]]
    assert "Alpine" in teams
    assert "Haas" in teams
    assert "Red Bull" not in teams


def test_compare_drivers_single_race(populated_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify intra-team battle in a single race."""
    db, store, _ = populated_env
    comparator = AlpinePerformanceComparator(db=db, parquet_store=store)

    comp = comparator.compare_drivers(season=2024, round_number=1)
    assert comp["constructor_id"] == "alpine"
    assert comp["driver_1"] == "GAS"
    assert comp["driver_2"] == "OCO"
    assert comp["finish_position_delta"] == -1  # Gasly P11 vs Ocon P12


def test_compare_recent_trend(populated_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify recent trend evaluation vs season baseline."""
    db, store, _ = populated_env
    comparator = AlpinePerformanceComparator(db=db, parquet_store=store)

    trend = comparator.compare_recent_trend(season=2024, current_round=1, last_n_races=3)
    assert trend["season"] == 2024
    assert trend["recent_avg_finish"] == pytest.approx(11.5, abs=0.1)
    assert trend["trend_status"] in ["STABLE", "IMPROVING", "DECLINING"]


def test_compare_across_seasons(populated_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify multi-season comparison with regulation era metadata."""
    db, store, _ = populated_env
    comparator = AlpinePerformanceComparator(db=db, parquet_store=store)

    seasons_data = comparator.compare_across_seasons(constructor_id="alpine", seasons=[2024])
    assert len(seasons_data) == 1
    row = seasons_data[0]
    assert row["season"] == 2024
    assert "Ground Effect" in row["regulation_era"]
    assert "total_starts" in row
