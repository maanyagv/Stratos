"""Chronological backtesting and empirical research evaluation for STRATOS.

Implements leakage-free sequential evaluation across historical seasons,
computing continuous metrics (MAE, RMSE), proper scoring rules (Brier score),
and empirical uncertainty calibration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from stratos.prediction.features import FeatureExtractor
from stratos.prediction.models import StratosRaceForecaster

if TYPE_CHECKING:
    from stratos.storage.database import StratosDB
    from stratos.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Summary metrics of a chronological backtesting experiment."""

    experiment_id: str
    model_version: str
    evaluated_races_count: int
    model_mae: float
    model_rmse: float
    baseline_mae: float
    baseline_rmse: float
    brier_score_points: float
    interval_coverage_pct: float
    evaluations: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert results to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "model_version": self.model_version,
            "evaluated_races_count": self.evaluated_races_count,
            "model_mae": self.model_mae,
            "model_rmse": self.model_rmse,
            "baseline_mae": self.baseline_mae,
            "baseline_rmse": self.baseline_rmse,
            "brier_score_points": self.brier_score_points,
            "interval_coverage_pct": self.interval_coverage_pct,
            "evaluations": self.evaluations,
        }


class ChronologicalBacktester:
    """Performs rigorous chronological backtesting without future data leakage."""

    def __init__(
        self,
        db: StratosDB,
        parquet_store: ParquetStore | None = None,
        forecaster: StratosRaceForecaster | None = None,
    ) -> None:
        """Initialize backtester.

        Parameters
        ----------
        db : StratosDB
            Database manager.
        parquet_store : ParquetStore or None
            Parquet store for practice lap access.
        forecaster : StratosRaceForecaster or None
            Forecasting engine. If None, initializes default StratosRaceForecaster.
        """
        self.db = db
        self.parquet_store = parquet_store
        self.forecaster = forecaster if forecaster is not None else StratosRaceForecaster()
        self.extractor = FeatureExtractor(db=self.db, parquet_store=self.parquet_store)

    def run_backtest(
        self,
        seasons: list[int],
        stage: str = "PRE_WEEKEND",
        constructor_id: str = "alpine",
        driver_code: str = "GAS",
        save_to_db: bool = True,
    ) -> BacktestResult:
        """Execute chronological backtesting across designated seasons.

        Parameters
        ----------
        seasons : list[int]
            List of championship years to evaluate sequentially.
        stage : str, default 'PRE_WEEKEND'
            Forecast cutoff stage.
        constructor_id : str, default 'alpine'
            Constructor under evaluation.
        driver_code : str, default 'GAS'
            Driver under evaluation.
        save_to_db : bool, default True
            Whether to persist the experiment run to StratosDB.

        Returns
        -------
        BacktestResult
            Comparative evaluation report.
        """
        import datetime

        exp_id = f"exp_backtest_{stage.lower()}_{int(datetime.datetime.now().timestamp())}"
        evaluations: list[dict[str, Any]] = []

        # Retrieve all historical races for the target constructor in chronological order
        all_races: list[dict[str, Any]] = []
        for s in sorted(seasons):
            s_races = self.db.query_races(season=s, constructor_id=constructor_id)
            all_races.extend(s_races)

        if not all_races:
            return BacktestResult(
                experiment_id=exp_id,
                model_version=self.forecaster.MODEL_VERSION,
                evaluated_races_count=0,
                model_mae=0.0,
                model_rmse=0.0,
                baseline_mae=0.0,
                baseline_rmse=0.0,
                brier_score_points=0.0,
                interval_coverage_pct=0.0,
                evaluations=[],
            )

        df_all = pd.DataFrame(all_races)
        # Distinct events by (season, round_number)
        event_tuples = (
            df_all[["season", "round_number", "event_name"]]
            .drop_duplicates()
            .to_dict("records")
        )

        model_errors = []
        baseline_errors = []
        brier_diffs = []
        inside_interval_flags = []

        for ev in event_tuples:
            s = int(ev["season"])
            rnd = int(ev["round_number"])
            name = str(ev["event_name"])

            # 1. Extract features strictly before cutoff
            feat = self.extractor.extract_features(
                season=s,
                round_number=rnd,
                stage=stage,
                driver_code=driver_code,
                constructor_id=constructor_id,
                event_name=name,
            )

            # 2. Generate forecast
            report = self.forecaster.forecast(feat)

            # 3. Query actual race outcome
            actual_records = df_all[
                (df_all["season"] == s)
                & (df_all["round_number"] == rnd)
                & (df_all["driver_code"] == driver_code)
            ]
            if actual_records.empty:
                # Fallback to any constructor driver in that race
                actual_records = df_all[
                    (df_all["season"] == s) & (df_all["round_number"] == rnd)
                ]

            if actual_records.empty or pd.isna(actual_records.iloc[0].get("finish_position")):
                continue

            actual_row = actual_records.iloc[0]
            actual_pos = float(actual_row["finish_position"])
            actual_pts = float(actual_row.get("points", 0.0))
            actual_points_scored = 1.0 if actual_pts > 0 else 0.0

            # Compute error metrics
            pred_f = report.expected_finish_position
            base_f = report.baseline_predicted_finish

            err_m = actual_pos - pred_f
            err_b = actual_pos - base_f

            model_errors.append(abs(err_m))
            baseline_errors.append(abs(err_b))

            # Brier Score = (predicted_probability - actual_binary)^2
            brier_diffs.append((report.points_probability - actual_points_scored) ** 2)

            # Empirical 90% Confidence Interval Check
            low_b, high_b = report.finish_position_interval
            inside = 1 if (low_b <= actual_pos <= high_b) else 0
            inside_interval_flags.append(inside)

            evaluations.append(
                {
                    "season": s,
                    "round_number": rnd,
                    "event_name": name,
                    "driver_code": actual_row.get("driver_code", driver_code),
                    "predicted_finish": pred_f,
                    "actual_finish": actual_pos,
                    "error": round(err_m, 2),
                    "baseline_finish": base_f,
                    "baseline_error": round(err_b, 2),
                    "points_probability": report.points_probability,
                    "actual_points": actual_pts,
                    "inside_interval": bool(inside),
                }
            )

        n_eval = len(model_errors)
        if n_eval == 0:
            m_mae = 0.0
            m_rmse = 0.0
            b_mae = 0.0
            b_rmse = 0.0
            brier = 0.0
            coverage = 0.0
        else:
            m_mae = round(float(np.mean(model_errors)), 3)
            m_rmse = round(float(np.sqrt(np.mean(np.array(model_errors) ** 2))), 3)
            b_mae = round(float(np.mean(baseline_errors)), 3)
            b_rmse = round(float(np.sqrt(np.mean(np.array(baseline_errors) ** 2))), 3)
            brier = round(float(np.mean(brier_diffs)), 4)
            coverage = round(float(np.mean(inside_interval_flags) * 100.0), 1)

        result = BacktestResult(
            experiment_id=exp_id,
            model_version=self.forecaster.MODEL_VERSION,
            evaluated_races_count=n_eval,
            model_mae=m_mae,
            model_rmse=m_rmse,
            baseline_mae=b_mae,
            baseline_rmse=b_rmse,
            brier_score_points=brier,
            interval_coverage_pct=coverage,
            evaluations=evaluations,
        )

        if save_to_db and n_eval > 0:
            self.db.save_experiment(
                {
                    "id": exp_id,
                    "name": f"Chronological Backtest ({stage})",
                    "description": (
                        f"Sequential walk-forward evaluation across {n_eval} races "
                        f"in seasons {seasons}."
                    ),
                    "config": {
                        "seasons": seasons,
                        "stage": stage,
                        "constructor": constructor_id,
                        "driver": driver_code,
                        "model_version": self.forecaster.MODEL_VERSION,
                    },
                    "train_seasons": seasons,
                    "test_seasons": seasons,
                    "metrics": {
                        "mae": m_mae,
                        "rmse": m_rmse,
                        "brier_score": brier,
                        "interval_coverage_pct": coverage,
                    },
                    "baseline_metrics": {
                        "baseline_mae": b_mae,
                        "baseline_rmse": b_rmse,
                    },
                    "is_reproducible": True,
                }
            )

        return result
