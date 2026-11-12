"""Unit tests for STRATOS SQLite and Parquet persistent storage subsystem."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore


@pytest.fixture
def temp_dir() -> Path:
    """Provide a temporary directory for isolated database and file tests."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        yield Path(tmp)


@pytest.fixture
def test_db(temp_dir: Path) -> StratosDB:
    """Provide an isolated StratosDB instance."""
    db_file = temp_dir / "test_stratos.db"
    return StratosDB(db_path=db_file)


@pytest.fixture
def test_parquet_store(temp_dir: Path) -> ParquetStore:
    """Provide an isolated ParquetStore instance."""
    p_dir = temp_dir / "processed"
    return ParquetStore(root_dir=p_dir)


def test_schema_initialization(test_db: StratosDB) -> None:
    """Verify tables and default data sources are created properly."""
    with test_db.get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        table_names = {row["name"] for row in tables}

    expected = {
        "data_sources",
        "events",
        "sessions",
        "session_results",
        "pit_stops",
        "race_control_events",
        "source_provenance",
        "ingestion_log",
        "data_quality_warnings",
        "predictions",
        "experiments",
        "metadata",
    }
    assert expected.issubset(table_names)

    # Check default sources seeded
    with test_db.get_connection() as conn:
        sources = conn.execute("SELECT id FROM data_sources;").fetchall()
        source_ids = {row["id"] for row in sources}
    assert "fastf1" in source_ids
    assert "alpine_official" in source_ids


def test_upsert_event_and_session(test_db: StratosDB) -> None:
    """Verify inserting and updating events and sessions."""
    event_dict = {
        "season": 2024,
        "round_number": 1,
        "event_name": "Bahrain Grand Prix",
        "country": "Bahrain",
        "location": "Sakhir",
        "event_date": "2024-03-02",
        "is_sprint": False,
    }
    event_id = test_db.upsert_event(event_dict)
    assert event_id == "2024_01_BAH"

    session_dict = {
        "event_id": event_id,
        "season": 2024,
        "round_number": 1,
        "session_type": "R",
        "session_name": "Bahrain Grand Prix Race",
        "total_laps": 57,
        "total_drivers": 20,
        "has_laps": 1,
        "has_weather": 1,
    }
    session_id = test_db.upsert_session(session_dict)
    assert session_id == "2024_01_R"

    # Save session results
    results = [
        {
            "driver_number": "10",
            "driver_code": "GAS",
            "driver_name": "Pierre Gasly",
            "constructor_id": "alpine",
            "constructor_name": "BWT Alpine F1 Team",
            "grid_position": 18,
            "finish_position": 18,
            "points": 0.0,
            "finish_status": "Finished",
            "fastest_lap_time": 95.2,
        },
        {
            "driver_number": "31",
            "driver_code": "OCO",
            "driver_name": "Esteban Ocon",
            "constructor_id": "alpine",
            "constructor_name": "BWT Alpine F1 Team",
            "grid_position": 19,
            "finish_position": 17,
            "points": 0.0,
            "finish_status": "Finished",
            "fastest_lap_time": 95.0,
        },
    ]
    saved_count = test_db.save_session_results(session_id, results)
    assert saved_count == 2

    # Query back results
    stored_results = test_db.get_session_results(session_id)
    assert len(stored_results) == 2
    assert stored_results[0]["driver_code"] == "OCO"  # P17 before P18


def test_provenance_and_logs(test_db: StratosDB) -> None:
    """Verify recording provenance, ingestion logs, and data quality warnings."""
    prov_id = test_db.record_provenance(
        {
            "dataset_key": "laps_2024_01_R",
            "source_id": "fastf1",
            "season": 2024,
            "record_count": 1140,
            "data_availability": "COMPLETE",
            "checksum": "abc123hash",
        }
    )
    assert prov_id.startswith("prov_")

    log_id = test_db.log_ingestion(
        status="SUCCESS",
        message="Test ingestion completed.",
        season=2024,
        round_number=1,
        session_type="R",
        records_ingested=1140,
        duration_seconds=1.2,
    )
    assert log_id > 0

    warn_id = test_db.log_data_warning(
        check_name="OUTLIER_PACE",
        severity="WARNING",
        message="Lap time > 107% of driver median.",
        session_id="2024_01_R",
        field_name="lap_time_seconds",
        raw_value="142.5",
    )
    assert warn_id > 0

    warnings = test_db.get_data_warnings(session_id="2024_01_R")
    assert len(warnings) == 1
    assert warnings[0]["check_name"] == "OUTLIER_PACE"


def test_predictions_persistence_and_evaluation(test_db: StratosDB) -> None:
    """Verify saving predictions without overwriting and recording actual outcomes."""
    pred_dict = {
        "prediction_cutoff": "2024-03-01T12:00:00Z",
        "stage": "PRE_RACE",
        "target_event_id": "2024_01_BAH",
        "target_season": 2024,
        "target_round": 1,
        "model_version": "ridge_v1.0",
        "target_type": "RACE_FINISH_POS",
        "predicted_value": 11.5,
        "interval_low": 9.0,
        "interval_high": 14.0,
        "distribution": {"P10": 0.15, "P11": 0.25, "P12": 0.20},
        "feature_values": {"pace_delta": 0.82, "reliability": 0.95},
        "assumptions": "Dry race, nominal pit stop time",
    }
    pred_id = test_db.save_prediction(pred_dict)
    assert pred_id.startswith("pred_")

    preds = test_db.get_predictions(target_event_id="2024_01_BAH", stage="PRE_RACE")
    assert len(preds) == 1
    assert preds[0]["predicted_value"] == 11.5
    assert preds[0]["is_evaluated"] == 0

    # Record actual outcome (e.g. driver finished P11)
    test_db.record_actual_outcome(pred_id, actual_value=11.0)
    updated_preds = test_db.get_predictions(target_event_id="2024_01_BAH")
    assert updated_preds[0]["is_evaluated"] == 1
    assert updated_preds[0]["actual_value"] == 11.0
    assert updated_preds[0]["error"] == -0.5  # actual - predicted = 11.0 - 11.5 = -0.5


def test_parquet_store_operations(test_parquet_store: ParquetStore) -> None:
    """Verify Parquet storage operations for laps and weather."""
    df_laps = pd.DataFrame(
        {
            "driver": ["GAS", "GAS", "OCO"],
            "lap_number": [1, 2, 1],
            "lap_time_seconds": [94.5, 93.8, 94.2],
            "compound": ["SOFT", "SOFT", "MEDIUM"],
            "is_clean_lap": [True, True, True],
        }
    )

    path = test_parquet_store.save_laps(2024, 1, "R", df_laps)
    assert path.is_file()
    assert test_parquet_store.has_laps(2024, 1, "R")

    loaded_df = test_parquet_store.load_laps(2024, 1, "R")
    assert len(loaded_df) == 3
    assert "lap_time_seconds" in loaded_df.columns
    assert loaded_df["driver"].tolist() == ["GAS", "GAS", "OCO"]

    # Datasets listing
    datasets = test_parquet_store.list_datasets()
    assert len(datasets) == 1
    assert datasets[0]["season"] == 2024
    assert datasets[0]["round_number"] == 1


def test_export_and_backup(test_db: StratosDB, temp_dir: Path) -> None:
    """Verify exporting tables to CSV and online SQLite database backup."""
    # Insert dummy event
    test_db.upsert_event(
        {
            "season": 2023,
            "round_number": 6,
            "event_name": "Monaco Grand Prix",
        }
    )

    # Export to CSV
    csv_file = temp_dir / "events_export.csv"
    out_csv = test_db.export_to_csv("events", csv_file)
    assert out_csv.is_file()
    df_csv = pd.read_csv(out_csv)
    assert len(df_csv) >= 1
    assert "Monaco Grand Prix" in df_csv["event_name"].values

    # Test database backup
    backup_dir = temp_dir / "backups"
    backup_file = test_db.create_backup(backup_dir)
    assert backup_file.is_file()
    assert backup_file.stat().st_size > 0
