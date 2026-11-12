"""Unit tests for ChronologicalBacktester research evaluation engine."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from stratos.prediction.backtesting import ChronologicalBacktester
from stratos.prediction.models import StratosRaceForecaster
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore


@pytest.fixture
def backtest_env() -> tuple[StratosDB, ParquetStore, Path]:
    """Provide database seeded with 5 historical rounds in 2024."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t_path = Path(tmp)
        db = StratosDB(db_path=t_path / "stratos.db")
        store = ParquetStore(root_dir=t_path / "processed")

        # Seed 5 rounds with known outcomes
        finishes = [12, 11, 10, 9, 8]
        points = [0.0, 0.0, 1.0, 2.0, 4.0]

        for idx, (fin, pts) in enumerate(zip(finishes, points, strict=True)):
            r_num = idx + 1
            ev_id = f"2024_{r_num:02d}_GP"
            db.upsert_event(
                {
                    "id": ev_id,
                    "season": 2024,
                    "round_number": r_num,
                    "event_name": f"Grand Prix {r_num}",
                }
            )
            s_id = f"2024_{r_num:02d}_R"
            db.upsert_session(
                {
                    "id": s_id,
                    "event_id": ev_id,
                    "season": 2024,
                    "round_number": r_num,
                    "session_type": "R",
                    "session_name": f"GP {r_num} Race",
                }
            )
            db.save_session_results(
                s_id,
                [
                    {
                        "driver_code": "GAS",
                        "driver_name": "Pierre Gasly",
                        "constructor_id": "alpine",
                        "constructor_name": "BWT Alpine F1 Team",
                        "finish_position": fin,
                        "points": pts,
                        "finish_status": "Finished",
                    }
                ],
            )

        yield db, store, t_path


def test_chronological_backtest_execution(
    backtest_env: tuple[StratosDB, ParquetStore, Path],
) -> None:
    """Verify sequential walk-forward backtest calculates MAE, RMSE, and Brier score."""
    db, store, _ = backtest_env
    forecaster = StratosRaceForecaster()
    backtester = ChronologicalBacktester(db=db, parquet_store=store, forecaster=forecaster)

    result = backtester.run_backtest(seasons=[2024], stage="PRE_WEEKEND", save_to_db=True)

    assert result.evaluated_races_count == 5
    assert result.model_mae >= 0.0
    assert result.model_rmse >= result.model_mae  # mathematical property: RMSE >= MAE
    assert 0.0 <= result.brier_score_points <= 1.0
    assert 0.0 <= result.interval_coverage_pct <= 100.0
    assert len(result.evaluations) == 5

    # Check that experiment record was saved to StratosDB
    experiments = db.get_experiments()
    assert len(experiments) >= 1
    assert experiments[0]["id"] == result.experiment_id
    assert "PRE_WEEKEND" in experiments[0]["name"]
