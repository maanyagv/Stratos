"""Formula 1 predictive models for qualifying pace, finish distribution, and points probability.

Implements interpretable baselines (HistoricalPaceBaseline) alongside regularized
Ridge regression models with calibrated prediction intervals and discretized position distributions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from sklearn.linear_model import Ridge

if TYPE_CHECKING:
    from stratos.prediction.features import FeatureVector
    from stratos.storage.database import StratosDB

logger = logging.getLogger(__name__)


@dataclass
class ForecastReport:
    """Consolidated forecast report across qualifying, race pace, and points outcomes."""

    target_event_id: str
    target_season: int
    target_round: int
    stage: str
    model_version: str
    prediction_cutoff: str
    qualifying_pace_delta_pct: float
    qualifying_interval: tuple[float, float]
    expected_finish_position: float
    finish_position_interval: tuple[float, float]
    points_probability: float
    podium_probability: float
    top_6_probability: float
    position_distribution: dict[str, float]
    feature_values: dict[str, float]
    assumptions: str
    baseline_predicted_finish: float

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary representation."""
        return {
            "target_event_id": self.target_event_id,
            "target_season": self.target_season,
            "target_round": self.target_round,
            "stage": self.stage,
            "model_version": self.model_version,
            "prediction_cutoff": self.prediction_cutoff,
            "qualifying_pace_delta_pct": self.qualifying_pace_delta_pct,
            "qualifying_interval": self.qualifying_interval,
            "expected_finish_position": self.expected_finish_position,
            "finish_position_interval": self.finish_position_interval,
            "points_probability": self.points_probability,
            "podium_probability": self.podium_probability,
            "top_6_probability": self.top_6_probability,
            "position_distribution": self.position_distribution,
            "feature_values": self.feature_values,
            "assumptions": self.assumptions,
            "baseline_predicted_finish": self.baseline_predicted_finish,
        }

    def save(self, db: StratosDB) -> list[str]:
        """Persist forecast records to database without overwriting historical runs.

        Parameters
        ----------
        db : StratosDB
            Database manager.

        Returns
        -------
        list[str]
            List of generated prediction record IDs.
        """
        import datetime

        now = datetime.datetime.now(datetime.UTC).isoformat()
        pred_ids = []

        # 1. Qualifying Prediction Record
        q_id = db.save_prediction(
            {
                "created_at": now,
                "prediction_cutoff": self.prediction_cutoff,
                "stage": self.stage,
                "target_event_id": self.target_event_id,
                "target_season": self.target_season,
                "target_round": self.target_round,
                "model_version": self.model_version,
                "target_type": "QUALIFYING_PACE",
                "predicted_value": self.qualifying_pace_delta_pct,
                "interval_low": self.qualifying_interval[0],
                "interval_high": self.qualifying_interval[1],
                "distribution": {},
                "feature_values": self.feature_values,
                "assumptions": self.assumptions,
            }
        )
        pred_ids.append(q_id)

        # 2. Race Finishing Position Record
        r_id = db.save_prediction(
            {
                "created_at": now,
                "prediction_cutoff": self.prediction_cutoff,
                "stage": self.stage,
                "target_event_id": self.target_event_id,
                "target_season": self.target_season,
                "target_round": self.target_round,
                "model_version": self.model_version,
                "target_type": "RACE_FINISH_POS",
                "predicted_value": self.expected_finish_position,
                "interval_low": self.finish_position_interval[0],
                "interval_high": self.finish_position_interval[1],
                "distribution": self.position_distribution,
                "feature_values": self.feature_values,
                "assumptions": self.assumptions,
            }
        )
        pred_ids.append(r_id)

        # 3. Points Probability Record
        p_id = db.save_prediction(
            {
                "created_at": now,
                "prediction_cutoff": self.prediction_cutoff,
                "stage": self.stage,
                "target_event_id": self.target_event_id,
                "target_season": self.target_season,
                "target_round": self.target_round,
                "model_version": self.model_version,
                "target_type": "POINTS_PROB",
                "predicted_value": self.points_probability,
                "interval_low": max(0.0, self.points_probability - 0.15),
                "interval_high": min(1.0, self.points_probability + 0.15),
                "distribution": {
                    "points": self.points_probability,
                    "top_6": self.top_6_probability,
                    "podium": self.podium_probability,
                },
                "feature_values": self.feature_values,
                "assumptions": self.assumptions,
            }
        )
        pred_ids.append(p_id)

        return pred_ids


class HistoricalPaceBaseline:
    """Interpretable historical baseline model using rolling averages."""

    def predict(self, feature_vector: FeatureVector) -> float:
        """Predict expected finish position using recent historical average finish."""
        f = feature_vector.features
        return float(f.get("recent_avg_finish", 12.0))


class StratosRaceForecaster:
    """Calibrated statistical prediction engine for Formula 1 race intelligence."""

    MODEL_VERSION: str = "stratos_ridge_v1.0"

    def __init__(self, alpha: float = 1.0) -> None:
        """Initialize the forecaster with regularized linear estimator.

        Parameters
        ----------
        alpha : float, default 1.0
            Ridge L2 regularization parameter.
        """
        self.alpha = alpha
        self.qualy_model = Ridge(alpha=self.alpha)
        self.finish_model = Ridge(alpha=self.alpha)
        self.baseline = HistoricalPaceBaseline()
        self._is_fitted = False
        self.qualy_rmse = 0.45  # default calibration std (seconds delta %)
        self.finish_rmse = 2.15  # default calibration std (positions)
        self._init_default_weights()

    def _init_default_weights(self) -> None:
        """Initialize weights based on historical domain telemetry priors."""
        # Feature names:
        # [0] recent_normalized_pace_delta
        # [1] recent_avg_finish
        # [2] recent_points_rate
        # [3] recent_reliability_rate
        # [4] season_avg_finish
        # [5] circuit_overtaking_difficulty
        # [6] circuit_downforce_demand
        # [7] circuit_deg_severity
        # [8] practice_pace_delta
        # [9] qualifying_grid_pos
        # [10] weather_rain_prob
        self.qualy_coef = np.array(
            [0.65, 0.05, -0.05, -0.02, 0.04, 0.0, 0.08, 0.02, 0.45, 0.0, 0.10]
        )
        self.qualy_intercept = 0.85  # Alpine typical baseline delta to pole in %

        self.finish_coef = np.array(
            [1.20, 0.35, -0.40, -1.80, 0.25, 1.10, 0.10, 0.15, 0.85, 0.65, 0.80]
        )
        self.finish_intercept = 3.20

    def fit(self, X: np.ndarray, y_qualy: np.ndarray, y_finish: np.ndarray) -> None:
        """Fit regularized models on historical training samples.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix (n_samples, n_features).
        y_qualy : np.ndarray
            Qualifying delta percentage targets.
        y_finish : np.ndarray
            Finishing position targets.
        """
        if len(X) >= 4:
            self.qualy_model.fit(X, y_qualy)
            q_preds = self.qualy_model.predict(X)
            self.qualy_rmse = max(0.20, float(np.sqrt(np.mean((y_qualy - q_preds) ** 2))))

            self.finish_model.fit(X, y_finish)
            f_preds = self.finish_model.predict(X)
            self.finish_rmse = max(1.20, float(np.sqrt(np.mean((y_finish - f_preds) ** 2))))

            self._is_fitted = True
            logger.info(
                "Fitted StratosRaceForecaster on %d samples (qualy_rmse=%.2f, finish_rmse=%.2f).",
                len(X),
                self.qualy_rmse,
                self.finish_rmse,
            )

    def forecast(
        self,
        feature_vector: FeatureVector,
        prediction_cutoff: str = "",
        assumptions: str = "",
    ) -> ForecastReport:
        """Generate a complete calibrated race forecast report.

        Parameters
        ----------
        feature_vector : FeatureVector
            Input features at the chosen cutoff stage.
        prediction_cutoff : str
            Timestamp cutoff string.
        assumptions : str
            Qualitative assumptions.

        Returns
        -------
        ForecastReport
            Complete predictive report with intervals and distribution.
        """
        x = feature_vector.as_array()
        expected_len = len(self.qualy_coef)
        if len(x) < expected_len:
            x = np.pad(x, (0, expected_len - len(x)))
        elif len(x) > expected_len:
            x = x[:expected_len]

        # 1. Qualifying Pace Prediction
        if self._is_fitted:
            raw_q = float(self.qualy_model.predict(x.reshape(1, -1))[0])
        else:
            raw_q = float(np.dot(x, self.qualy_coef) + self.qualy_intercept)
        qualy_pred = round(max(0.0, raw_q), 3)
        qualy_interval = (
            round(max(0.0, qualy_pred - 1.645 * self.qualy_rmse), 3),
            round(qualy_pred + 1.645 * self.qualy_rmse, 3),
        )

        # 2. Race Finishing Position Prediction
        if self._is_fitted:
            raw_f = float(self.finish_model.predict(x.reshape(1, -1))[0])
        else:
            # Stage-aware weighting: if grid position is available, weight it heavily
            if feature_vector.stage in ["POST_QUALIFYING", "PRE_RACE"]:
                grid = float(
                    feature_vector.features.get(
                        "qualifying_grid_pos",
                        feature_vector.features.get("grid_position", 11.0),
                    )
                )
                base_f = float(np.dot(x, self.finish_coef) + self.finish_intercept)
                raw_f = 0.65 * grid + 0.35 * base_f
            else:
                raw_f = float(np.dot(x, self.finish_coef) + self.finish_intercept)

        expected_finish = round(float(np.clip(raw_f, 1.0, 20.0)), 2)
        finish_interval = (
            round(float(np.clip(expected_finish - 1.645 * self.finish_rmse, 1.0, 20.0)), 1),
            round(float(np.clip(expected_finish + 1.645 * self.finish_rmse, 1.0, 20.0)), 1),
        )

        # 3. Calibrated Position Probability Distribution across 20 positions
        # Uses a discretized Gaussian kernel centered at expected_finish with std finish_rmse
        positions = np.arange(1, 21, dtype=float)
        sigma = max(1.5, self.finish_rmse)
        logits = -0.5 * ((positions - expected_finish) / sigma) ** 2
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / np.sum(exp_logits)

        dist_map = {f"P{i}": round(float(probs[i - 1]), 4) for i in range(1, 21)}

        # 4. Championship Outcome Probabilities
        points_prob = round(float(np.sum(probs[:10])), 3)  # P1 to P10
        top_6_prob = round(float(np.sum(probs[:6])), 3)  # P1 to P6
        podium_prob = round(float(np.sum(probs[:3])), 3)  # P1 to P3

        # 5. Baseline Comparison
        base_pred = round(self.baseline.predict(feature_vector), 2)

        default_assump = (
            assumptions
            if assumptions
            else f"Forecast generated at {feature_vector.stage} cutoff. Standard dry setup assumed."
        )

        return ForecastReport(
            target_event_id=feature_vector.target_event_id,
            target_season=feature_vector.season,
            target_round=feature_vector.round_number,
            stage=feature_vector.stage,
            model_version=self.MODEL_VERSION,
            prediction_cutoff=prediction_cutoff,
            qualifying_pace_delta_pct=qualy_pred,
            qualifying_interval=qualy_interval,
            expected_finish_position=expected_finish,
            finish_position_interval=finish_interval,
            points_probability=points_prob,
            podium_probability=podium_prob,
            top_6_probability=top_6_prob,
            position_distribution=dist_map,
            feature_values=feature_vector.features,
            assumptions=default_assump,
            baseline_predicted_finish=base_pred,
        )
