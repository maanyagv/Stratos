"""Unit tests for FeatureExtractor and StratosRaceForecaster predictive models."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from stratos.prediction.features import FeatureExtractor, FeatureVector
from stratos.prediction.models import (
    HistoricalPaceBaseline,
    StratosRaceForecaster,
)
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore


@pytest.fixture
def test_setup() -> tuple[StratosDB, ParquetStore, Path]:
    """Provide isolated database and parquet store with seeded history."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t_path = Path(tmp)
        db = StratosDB(db_path=t_path / "stratos.db")
        store = ParquetStore(root_dir=t_path / "processed")

        # Seed 3 prior races in 2024
        for r_num in [1, 2, 3]:
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
            # Gasly finished P11, P10, P9
            db.save_session_results(
                s_id,
                [
                    {
                        "driver_code": "GAS",
                        "driver_name": "Pierre Gasly",
                        "constructor_id": "alpine",
                        "constructor_name": "BWT Alpine F1 Team",
                        "finish_position": 12 - r_num,
                        "points": float(r_num - 1),
                        "finish_status": "Finished",
                    }
                ],
            )

        yield db, store, t_path


def test_feature_extractor_no_leakage(
    test_setup: tuple[StratosDB, ParquetStore, Path],
) -> None:
    """Verify that feature extraction strictly uses history prior to cutoff."""
    db, store, _ = test_setup
    extractor = FeatureExtractor(db=db, parquet_store=store)

    # Extract for Round 4 (rounds 1, 2, 3 should be used)
    feat_r4 = extractor.extract_features(
        season=2024,
        round_number=4,
        stage="PRE_WEEKEND",
        driver_code="GAS",
        event_name="Silverstone Grand Prix",
    )
    # Gasly finished 11, 10, 9 -> mean is 10.0
    assert feat_r4.features["recent_avg_finish"] == pytest.approx(10.0, abs=0.01)
    assert feat_r4.features["practice_pace_delta"] == 0.0  # not available at pre-weekend
    assert feat_r4.features["circuit_downforce_demand"] > 0

    # Extract for Round 2 (only round 1 should be used)
    feat_r2 = extractor.extract_features(
        season=2024,
        round_number=2,
        stage="PRE_WEEKEND",
        driver_code="GAS",
        event_name="Saudi Grand Prix",
    )
    # Only round 1 (P11) was prior to round 2
    assert feat_r2.features["recent_avg_finish"] == 11.0


def test_forecaster_predictions_and_distribution(
    test_setup: tuple[StratosDB, ParquetStore, Path],
) -> None:
    """Verify forecast intervals, probability distributions, and outcome bounds."""
    db, store, _ = test_setup
    extractor = FeatureExtractor(db=db, parquet_store=store)
    forecaster = StratosRaceForecaster()

    feat = extractor.extract_features(
        season=2024,
        round_number=4,
        stage="PRE_WEEKEND",
        driver_code="GAS",
        event_name="Bahrain Grand Prix",
    )
    report = forecaster.forecast(feat, prediction_cutoff="2024-04-01T10:00:00Z")

    # 1. Qualifying predictions
    assert report.qualifying_pace_delta_pct >= 0.0
    q_low, q_high = report.qualifying_interval
    assert q_low <= report.qualifying_pace_delta_pct <= q_high

    # 2. Race finish predictions
    assert 1.0 <= report.expected_finish_position <= 20.0
    f_low, f_high = report.finish_position_interval
    assert f_low <= report.expected_finish_position <= f_high

    # 3. Position distribution must sum to 1.0
    dist_sum = sum(report.position_distribution.values())
    assert pytest.approx(dist_sum, abs=0.01) == 1.0
    assert len(report.position_distribution) == 20

    # 4. Monotonicity of probability outcomes: P(Win) <= P(Podium) <= P(Top6) <= P(Points) <= 1.0
    assert 0.0 <= report.podium_probability <= report.top_6_probability
    assert report.top_6_probability <= report.points_probability <= 1.0

    # 5. Baseline comparison
    assert report.baseline_predicted_finish == 10.0


def test_forecast_persistence_to_db(
    test_setup: tuple[StratosDB, ParquetStore, Path],
) -> None:
    """Verify saving forecast generates three non-destructive database records."""
    db, store, _ = test_setup
    extractor = FeatureExtractor(db=db, parquet_store=store)
    forecaster = StratosRaceForecaster()

    feat = extractor.extract_features(season=2024, round_number=4, stage="PRE_WEEKEND")
    report = forecaster.forecast(feat, prediction_cutoff="2024-04-01T10:00:00Z")

    pred_ids = report.save(db)
    assert len(pred_ids) == 3

    # Check predictions in DB
    all_preds = db.get_predictions(target_event_id=report.target_event_id)
    assert len(all_preds) == 3
    target_types = {p["target_type"] for p in all_preds}
    assert target_types == {"QUALIFYING_PACE", "RACE_FINISH_POS", "POINTS_PROB"}


def test_forecaster_fit_learning() -> None:
    """Verify fitting forecaster on training samples updates residual standard deviations."""
    forecaster = StratosRaceForecaster()
    # Synthetic samples
    X = np.random.RandomState(42).randn(10, 11)
    y_q = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 0.6, 0.7, 0.8, 0.9, 1.0])
    y_f = np.array([8.0, 9.0, 10.0, 11.0, 12.0, 9.0, 10.0, 11.0, 12.0, 13.0])

    forecaster.fit(X, y_q, y_f)
    assert forecaster._is_fitted is True
    assert forecaster.qualy_rmse > 0
    assert forecaster.finish_rmse > 0


def test_baseline_pace_model() -> None:
    """Verify HistoricalPaceBaseline predicts rolling recent average."""
    baseline = HistoricalPaceBaseline()
    feat = FeatureVector(
        target_event_id="2024-01-R",
        season=2024,
        round_number=1,
        stage="PRE_WEEKEND",
        driver_code="GAS",
        feature_names=["recent_avg_finish"],
        features={"recent_avg_finish": 11.2},
    )
    pred = baseline.predict(feat)
    assert pred == 11.2

    # And with default fallback when feature is missing
    feat_empty = FeatureVector(
        target_event_id="2024-01-R",
        season=2024,
        round_number=1,
        stage="PRE_WEEKEND",
        driver_code="GAS",
        feature_names=[],
        features={},
    )
    assert baseline.predict(feat_empty) == 12.0
