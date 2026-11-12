"""Unit tests for STRATOS ingestion pipeline and data validator."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stratos.ingestion.pipeline import IngestionPipeline
from stratos.ingestion.validator import CoverageReporter, DataValidator
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore


@pytest.fixture
def temp_env() -> tuple[StratosDB, ParquetStore, Path]:
    """Provide isolated DB, ParquetStore, and cache directory."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t_path = Path(tmp)
        db = StratosDB(db_path=t_path / "stratos.db")
        store = ParquetStore(root_dir=t_path / "processed")
        cache = t_path / "cache"
        yield db, store, cache


def test_validator_clean_lap_detection() -> None:
    """Verify that DataValidator correctly flags clean laps vs pit and outlier laps."""
    df_raw = pd.DataFrame(
        {
            "Driver": ["GAS", "GAS", "GAS", "GAS", "GAS"],
            "DriverNumber": ["10", "10", "10", "10", "10"],
            "Team": ["Alpine", "Alpine", "Alpine", "Alpine", "Alpine"],
            "LapNumber": [1, 2, 3, 4, 5],
            "LapTime": [
                pd.Timedelta("92.5s"),
                pd.Timedelta("92.8s"),
                pd.Timedelta("125.0s"),  # In lap / pit entry
                pd.Timedelta("93.0s"),
                pd.Timedelta("115.0s"),  # Pace outlier > 107%
            ],
            "PitInTime": [pd.NaT, pd.NaT, pd.Timedelta("120.0s"), pd.NaT, pd.NaT],
            "PitOutTime": [pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.NaT],
            "TrackStatus": ["1", "1", "1", "1", "1"],
            "IsAccurate": [True, True, True, True, True],
            "Compound": ["SOFT", "SOFT", "SOFT", "MEDIUM", "MEDIUM"],
            "TyreLife": [1, 2, 3, 1, 2],
        }
    )

    clean_df, warnings = DataValidator.validate_laps(df_raw, "2024_01_R")
    assert "is_clean_lap" in clean_df.columns
    # Laps 1, 2, 4 should be clean. Lap 3 (PitInTime not NaT) and Lap 5 (outlier > 107%) should not.
    lap1_clean = clean_df.loc[clean_df["lap_number"] == 1, "is_clean_lap"].values[0]
    assert bool(lap1_clean) is True
    assert bool(clean_df.loc[clean_df["lap_number"] == 3, "is_clean_lap"].values[0]) is False
    assert bool(clean_df.loc[clean_df["lap_number"] == 5, "is_clean_lap"].values[0]) is False


def test_validator_negative_tyre_life_correction() -> None:
    """Verify that negative tyre life is corrected to 0 and logs an error warning."""
    df_raw = pd.DataFrame(
        {
            "Driver": ["OCO"],
            "LapNumber": [1],
            "LapTime": [pd.Timedelta("93.5s")],
            "Compound": ["HARD"],
            "TyreLife": [-5],
        }
    )
    clean_df, warnings = DataValidator.validate_laps(df_raw, "2024_01_R")
    assert clean_df["tyre_life"].iloc[0] == 0
    assert any(w["check_name"] == "NEGATIVE_TYRE_LIFE" for w in warnings)


def test_validator_results() -> None:
    """Verify results validation catches improbable finish positions and duplicates."""
    raw_results = [
        {
            "driver_code": "GAS",
            "driver_name": "Pierre Gasly",
            "constructor_id": "alpine",
            "constructor_name": "BWT Alpine F1 Team",
            "grid_position": 10,
            "finish_position": 9,
            "points": 2.0,
        },
        {
            "driver_code": "GAS",  # Duplicate driver
            "driver_name": "Pierre Gasly",
            "constructor_id": "alpine",
            "constructor_name": "BWT Alpine F1 Team",
            "grid_position": 10,
            "finish_position": 9,
            "points": 2.0,
        },
        {
            "driver_code": "OCO",
            "driver_name": "Esteban Ocon",
            "constructor_id": "alpine",
            "constructor_name": "BWT Alpine F1 Team",
            "grid_position": 12,
            "finish_position": 35,  # Improbable position
            "points": -1.0,  # Negative points
        },
    ]

    cleaned, warnings = DataValidator.validate_results(raw_results, "2024_01_R")
    assert len(cleaned) == 2  # Duplicate GAS skipped
    assert any(w["check_name"] == "DUPLICATE_DRIVER_RESULT" for w in warnings)
    assert any(w["check_name"] == "IMPROBABLE_FINISH_POSITION" for w in warnings)
    assert any(w["check_name"] == "NEGATIVE_POINTS" for w in warnings)

    oco = [r for r in cleaned if r["driver_code"] == "OCO"][0]
    assert oco["points"] == 0.0


def test_pipeline_ingest_session_offline(
    temp_env: tuple[StratosDB, ParquetStore, Path],
) -> None:
    """Verify full ingestion workflow with mocked FastF1 session (100% offline)."""
    db, store, cache = temp_env
    pipeline = IngestionPipeline(db=db, parquet_store=store, cache_dir=cache)

    # Create mock session
    mock_session = MagicMock()
    mock_session.date = "2024-03-02"
    mock_session.event = {"EventName": "Bahrain Grand Prix"}

    mock_session.results = pd.DataFrame(
        {
            "DriverNumber": ["10", "31"],
            "Abbreviation": ["GAS", "OCO"],
            "FullName": ["Pierre Gasly", "Esteban Ocon"],
            "TeamName": ["Alpine", "Alpine"],
            "GridPosition": [15, 16],
            "Position": [11, 12],
            "ClassifiedPosition": ["11", "12"],
            "Points": [0.0, 0.0],
            "Status": ["Finished", "Finished"],
            "Time": [pd.Timedelta("5600.0s"), pd.Timedelta("5605.0s")],
            "FastestLapTime": [pd.Timedelta("95.1s"), pd.Timedelta("95.3s")],
            "FastestLapRank": [10, 12],
            "Q1": [None, None],
            "Q2": [None, None],
            "Q3": [None, None],
        }
    )

    mock_session.laps = pd.DataFrame(
        {
            "Driver": ["GAS", "OCO"],
            "DriverNumber": ["10", "31"],
            "Team": ["Alpine", "Alpine"],
            "LapNumber": [1, 1],
            "LapTime": [pd.Timedelta("95.1s"), pd.Timedelta("95.3s")],
            "Compound": ["SOFT", "MEDIUM"],
            "TyreLife": [1, 1],
            "PitInTime": [pd.NaT, pd.NaT],
            "PitOutTime": [pd.NaT, pd.NaT],
            "TrackStatus": ["1", "1"],
            "IsAccurate": [True, True],
        }
    )

    mock_session.weather_data = pd.DataFrame(
        {
            "AirTemp": [22.5],
            "TrackTemp": [32.0],
            "Humidity": [45.0],
            "Pressure": [1013.2],
            "WindSpeed": [3.5],
            "WindDirection": [180],
            "Rainfall": [False],
        }
    )

    mock_session.race_control_messages = pd.DataFrame(
        {
            "Lap": [1],
            "Time": ["15:05:00"],
            "Category": ["Flag"],
            "Status": ["CLEAR"],
            "Message": ["TRACK CLEAR"],
        }
    )

    with patch("stratos.ingestion.pipeline.load_session", return_value=mock_session):
        res = pipeline.ingest_session(season=2024, round_number=1, session_type="R")
        assert res.status in ["SUCCESS", "WARNING"]
        assert res.records_ingested > 0

        # Verify Parquet files created
        assert store.has_laps(2024, 1, "R")
        assert store.has_weather(2024, 1, "R")

        # Verify database records
        stored_results = db.get_session_results("2024_01_R")
        assert len(stored_results) == 2
        assert stored_results[0]["driver_code"] == "GAS"

        # Check coverage report
        report = CoverageReporter.generate_report(db, store)
        assert len(report["seasons"]) == 1
        assert report["total_results"] == 2
        assert report["parquet_files_count"] >= 1

        # Test duplicate skipping (force=False)
        res_dup = pipeline.ingest_session(
            season=2024, round_number=1, session_type="R", force=False
        )
        assert res_dup.status == "SKIPPED"
