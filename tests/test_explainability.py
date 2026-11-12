"""Unit tests for the explainability engine and prediction evaluator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from stratos.explainability.explainer import (
    PredictionEvaluator,
    PredictionExplainer,
)
from stratos.prediction.features import FeatureExtractor, FeatureVector
from stratos.prediction.models import StratosRaceForecaster
from stratos.storage.database import StratosDB


@pytest.fixture
def temp_db() -> tuple[StratosDB, Path]:
    """Provide temporary isolated StratosDB for evaluator tests."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        p = Path(tmp) / "stratos.db"
        db = StratosDB(db_path=p)
        yield db, p


def test_explainer_synthetic_report() -> None:
    """Verify PredictionExplainer generates attributions, uncertainty, and markdown."""
    forecaster = StratosRaceForecaster()
    explainer = PredictionExplainer()

    feat = FeatureVector(
        target_event_id="2024_05_CHN",
        season=2024,
        round_number=5,
        stage="POST_QUALIFYING",
        driver_code="GAS",
        feature_names=FeatureExtractor.FEATURE_NAMES,
        features={
            "recent_normalized_pace_delta": 0.95,
            "recent_avg_finish": 9.5,
            "recent_points_rate": 0.6,
            "recent_reliability_rate": 1.0,
            "season_avg_finish": 10.2,
            "circuit_overtaking_difficulty": 0.5,
            "circuit_downforce_demand": 0.6,
            "circuit_deg_severity": 0.7,
            "practice_pace_delta": 0.90,
            "qualifying_grid_pos": 8.0,
            "weather_rain_prob": 0.0,
        },
    )

    report = forecaster.forecast(feat, prediction_cutoff="2024-04-20T16:00:00Z")
    explanation = explainer.explain_forecast(
        report, event_name="Chinese Grand Prix", circuit_name="Shanghai International Circuit"
    )

    # 1. Structure assertions
    assert explanation.target_event_id == "2024_05_CHN"
    assert explanation.event_name == "Chinese Grand Prix"
    assert explanation.stage == "POST_QUALIFYING"
    assert len(explanation.feature_impacts) >= 4

    # 2. Key drivers
    assert len(explanation.positive_drivers) > 0
    # Grid position 8 is better than ref 11, so it should be favorable
    grid_imp = next(
        (
            f
            for f in explanation.feature_impacts
            if f.feature_name in ["grid_position", "qualifying_grid_pos"]
        ),
        None,
    )
    assert grid_imp is not None
    assert grid_imp.impact_positions < 0  # Improves position (lower number)
    assert grid_imp.direction == "FAVORABLE"

    # 3. Uncertainty factors
    assert len(explanation.uncertainty_factors) >= 1

    # 4. Midfield rivals
    assert len(explanation.rival_benchmarks) >= 3
    constructors = {r.constructor_name for r in explanation.rival_benchmarks}
    assert "Haas F1 Team" in constructors
    assert "Williams Racing" in constructors

    # 5. Historical analogues
    assert len(explanation.historical_analogues) >= 1

    # 6. Markdown representation
    md = explanation.to_markdown()
    assert "STRATOS Race Forecast Intelligence" in md
    assert "Measurable Feature Attribution" in md
    assert "Midfield Rival Contenders" in md
    assert "Viry-Châtillon" in md


def test_prediction_evaluator_metrics(temp_db: tuple[StratosDB, Path]) -> None:
    """Verify PredictionEvaluator computes accurate MAE, RMSE, coverage %, and Brier score."""
    db, _ = temp_db
    evaluator = PredictionEvaluator(db)

    # Empty DB state
    empty_res = evaluator.evaluate_saved_predictions()
    assert empty_res["count"] == 0
    assert empty_res["mae"] is None

    # Save 3 predictions with actual values
    # Pred 1: Pred P10, Actual P11, Interval [P8, P13] (Inside)
    p1 = db.save_prediction(
        {
            "created_at": "2024-03-01T10:00:00Z",
            "prediction_cutoff": "2024-03-01T09:00:00Z",
            "stage": "PRE_RACE",
            "target_event_id": "2024_01_BAH",
            "target_season": 2024,
            "target_round": 1,
            "model_version": "v1.0",
            "target_type": "RACE_FINISH_POS",
            "predicted_value": 10.0,
            "interval_low": 8.0,
            "interval_high": 13.0,
            "actual_value": 11.0,
            "is_evaluated": 1,
            "error": 1.0,
        }
    )

    # Pred 2: Pred P9, Actual P9, Interval [P7, P12] (Inside)
    p2 = db.save_prediction(
        {
            "created_at": "2024-03-08T10:00:00Z",
            "prediction_cutoff": "2024-03-08T09:00:00Z",
            "stage": "PRE_RACE",
            "target_event_id": "2024_02_SAU",
            "target_season": 2024,
            "target_round": 2,
            "model_version": "v1.0",
            "target_type": "RACE_FINISH_POS",
            "predicted_value": 9.0,
            "interval_low": 7.0,
            "interval_high": 12.0,
            "actual_value": 9.0,
            "is_evaluated": 1,
            "error": 0.0,
        }
    )

    # Pred 3: Pred P12, Actual P16, Interval [P10, P14] (Outside)
    p3 = db.save_prediction(
        {
            "created_at": "2024-03-22T10:00:00Z",
            "prediction_cutoff": "2024-03-22T09:00:00Z",
            "stage": "PRE_RACE",
            "target_event_id": "2024_03_AUS",
            "target_season": 2024,
            "target_round": 3,
            "model_version": "v1.0",
            "target_type": "RACE_FINISH_POS",
            "predicted_value": 12.0,
            "interval_low": 10.0,
            "interval_high": 14.0,
            "actual_value": 16.0,
            "is_evaluated": 1,
            "error": 4.0,
        }
    )
    assert p1 and p2 and p3

    # Pred 4: Points probability 0.70, scored points (1.0)
    db.save_prediction(
        {
            "created_at": "2024-03-01T10:00:00Z",
            "prediction_cutoff": "2024-03-01T09:00:00Z",
            "stage": "PRE_RACE",
            "target_event_id": "2024_01_BAH",
            "target_season": 2024,
            "target_round": 1,
            "model_version": "v1.0",
            "target_type": "POINTS_PROB",
            "predicted_value": 0.70,
            "interval_low": 0.55,
            "interval_high": 0.85,
            "actual_value": 1.0,
            "is_evaluated": 1,
            "error": 0.30,
        }
    )

    metrics = evaluator.evaluate_saved_predictions(target_type="RACE_FINISH_POS")
    assert metrics["count"] == 3
    # Errors: [1.0, 0.0, 4.0] -> MAE = (1+0+4)/3 = 1.667
    assert metrics["mae"] == pytest.approx(1.667, abs=0.01)
    # RMSE: sqrt((1 + 0 + 16)/3) = sqrt(5.667) = 2.380
    assert metrics["rmse"] == pytest.approx(2.380, abs=0.01)
    # Coverage: 2 out of 3 inside interval -> 66.7%
    assert metrics["interval_coverage_pct"] == pytest.approx(66.7, abs=0.1)
    # Brier score for points: (0.7 - 1.0)^2 = 0.09
    assert metrics["brier_score"] == pytest.approx(0.09, abs=0.01)


def test_auto_evaluate_pending_with_db_results(temp_db: tuple[StratosDB, Path]) -> None:
    """Verify auto_evaluate_pending links pending predictions with imported session results."""
    db, _ = temp_db
    evaluator = PredictionEvaluator(db)

    # 1. Setup session results for 2024 Round 1 Race
    ev_id = "2024_01_BAH"
    sess_id = "2024_01_BAH_R"
    db.upsert_event(
        {
            "id": ev_id,
            "season": 2024,
            "round_number": 1,
            "event_name": "Bahrain Grand Prix",
            "country": "Bahrain",
            "location": "Sakhir",
            "event_date": "2024-03-02",
        }
    )
    db.upsert_session(
        {
            "id": sess_id,
            "event_id": ev_id,
            "season": 2024,
            "round_number": 1,
            "session_type": "Race",
            "session_date": "2024-03-02",
        }
    )

    db.save_session_results(
        sess_id,
        [
            {
                "driver_code": "GAS",
                "driver_name": "Pierre Gasly",
                "constructor_id": "alpine",
                "constructor_name": "Alpine",
                "grid_position": 10,
                "finish_position": 9,
                "points": 2.0,
                "finish_status": "Finished",
            }
        ],
    )

    # 2. Save an unevaluated prediction
    pred_id = db.save_prediction(
        {
            "created_at": "2024-03-01T12:00:00Z",
            "prediction_cutoff": "2024-03-01T10:00:00Z",
            "stage": "PRE_RACE",
            "target_event_id": ev_id,
            "target_season": 2024,
            "target_round": 1,
            "model_version": "v1.0",
            "target_type": "RACE_FINISH_POS",
            "predicted_value": 11.0,
            "interval_low": 8.0,
            "interval_high": 14.0,
            "is_evaluated": 0,
        }
    )

    # 3. Auto-evaluate
    num_updated = evaluator.auto_evaluate_pending()
    assert num_updated == 1

    # 4. Check DB row updated
    updated = db.get_predictions(target_event_id=ev_id)
    target = next((p for p in updated if p["id"] == pred_id), None)
    assert target is not None
    assert target["is_evaluated"] == 1
    assert target["actual_value"] == 9.0
    assert target["error"] == -2.0  # 9.0 - 11.0
