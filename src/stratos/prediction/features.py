"""Leakage-free feature engineering for Formula 1 performance forecasting.

Builds calibrated feature vectors at four standardized prediction stages:
PRE_WEEKEND, POST_PRACTICE, POST_QUALIFYING, and PRE_RACE, strictly preventing future leakage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from stratos.alpine.metrics import calculate_clean_lap_pace, calculate_qualifying_performance

if TYPE_CHECKING:
    from stratos.storage.database import StratosDB
    from stratos.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

PREDICTION_STAGES = (
    "PRE_WEEKEND",
    "POST_PRACTICE",
    "POST_QUALIFYING",
    "PRE_RACE",
)


@dataclass
class FeatureVector:
    """Standardized numerical features for model inference and training."""

    season: int
    round_number: int
    stage: str
    target_event_id: str
    driver_code: str
    feature_names: list[str]
    features: dict[str, float]

    def as_array(self) -> np.ndarray:
        """Return feature values in standardized column order."""
        return np.array([self.features[k] for k in self.feature_names], dtype=float)


class FeatureExtractor:
    """Extracts features strictly respecting historical temporal boundaries."""

    CIRCUIT_CHARACTERISTICS: dict[str, dict[str, float]] = {
        "bahrain": {
            "overtaking_difficulty": 0.35, "downforce_demand": 0.60, "deg_severity": 0.85
        },
        "saudi": {
            "overtaking_difficulty": 0.45, "downforce_demand": 0.40, "deg_severity": 0.40
        },
        "australia": {
            "overtaking_difficulty": 0.55, "downforce_demand": 0.65, "deg_severity": 0.50
        },
        "japan": {
            "overtaking_difficulty": 0.65, "downforce_demand": 0.85, "deg_severity": 0.75
        },
        "monaco": {
            "overtaking_difficulty": 0.95, "downforce_demand": 0.95, "deg_severity": 0.20
        },
        "silverstone": {
            "overtaking_difficulty": 0.40, "downforce_demand": 0.80, "deg_severity": 0.70
        },
        "spa": {
            "overtaking_difficulty": 0.30, "downforce_demand": 0.50, "deg_severity": 0.65
        },
        "monza": {
            "overtaking_difficulty": 0.25, "downforce_demand": 0.15, "deg_severity": 0.45
        },
    }

    FEATURE_NAMES: list[str] = [
        "recent_normalized_pace_delta",
        "recent_avg_finish",
        "recent_points_rate",
        "recent_reliability_rate",
        "season_avg_finish",
        "circuit_overtaking_difficulty",
        "circuit_downforce_demand",
        "circuit_deg_severity",
        "practice_pace_delta",
        "qualifying_grid_pos",
        "weather_rain_prob",
    ]

    def __init__(self, db: StratosDB, parquet_store: ParquetStore | None = None) -> None:
        """Initialize FeatureExtractor.

        Parameters
        ----------
        db : StratosDB
            Database manager for querying historical results.
        parquet_store : ParquetStore or None
            Parquet store for practice and session lap queries.
        """
        self.db = db
        self.parquet_store = parquet_store

    def extract_features(
        self,
        season: int,
        round_number: int,
        stage: str = "PRE_WEEKEND",
        driver_code: str = "GAS",
        constructor_id: str = "alpine",
        event_name: str = "",
        weather_rain_prob: float = 0.0,
    ) -> FeatureVector:
        """Build feature vector strictly using data available before the cutoff stage.

        Parameters
        ----------
        season : int
            Target championship year.
        round_number : int
            Target round number.
        stage : str, default 'PRE_WEEKEND'
            Forecast stage ('PRE_WEEKEND', 'POST_PRACTICE', 'POST_QUALIFYING', 'PRE_RACE').
        driver_code : str, default 'GAS'
            Driver identifier.
        constructor_id : str, default 'alpine'
            Constructor identifier.
        event_name : str
            Grand Prix name for circuit characteristics lookup.
        weather_rain_prob : float, default 0.0
            Documented rain probability.

        Returns
        -------
        FeatureVector
            Calibrated numerical feature vector.
        """
        if stage not in PREDICTION_STAGES:
            raise ValueError(f"Invalid stage '{stage}'. Must be one of: {PREDICTION_STAGES}")

        target_event_id = f"{season}_{round_number:02d}_{event_name[:3].upper()}"

        # 1. Query strictly historical races prior to this event (NO LEAKAGE)
        prior_races = self._get_strictly_prior_races(
            season=season, round_number=round_number, constructor_id=constructor_id
        )

        # Baseline metrics over recent history (last 3-5 races)
        recent_races = prior_races[-5:] if len(prior_races) >= 5 else prior_races

        if recent_races:
            fin_positions = [
                float(r["finish_position"])
                for r in recent_races
                if r.get("finish_position") is not None
            ]
            recent_avg_finish = float(np.mean(fin_positions)) if fin_positions else 12.0

            total_pts = sum(float(r.get("points", 0.0)) for r in recent_races)
            recent_points_rate = total_pts / len(recent_races)

            classified_cnt = sum(
                1
                for r in recent_races
                if "finished" in str(r.get("finish_status", "")).lower()
                or "+" in str(r.get("finish_status", ""))
            )
            recent_reliability_rate = classified_cnt / len(recent_races)
        else:
            recent_avg_finish = 12.0
            recent_points_rate = 0.0
            recent_reliability_rate = 0.85

        if prior_races:
            all_fin = [
                float(r["finish_position"])
                for r in prior_races
                if r.get("finish_position") is not None
            ]
            season_avg_finish = float(np.mean(all_fin)) if all_fin else recent_avg_finish
        else:
            season_avg_finish = recent_avg_finish

        # Recent clean pace delta (proxy: difference of average finish from midfield center 10.5)
        recent_pace_delta = round((recent_avg_finish - 10.5) * 0.12, 3)

        # 2. Circuit characteristics lookup
        circuit_info = self._get_circuit_characteristics(event_name)

        # 3. Stage-gated features (Strict Leakage Prevention)
        practice_pace_delta = 0.0
        if stage in ["POST_PRACTICE", "POST_QUALIFYING", "PRE_RACE"] and self.parquet_store:
            # Check for target event FP2 clean pace if ingested
            fp2_laps = self.parquet_store.load_laps(season, round_number, "FP2")
            if not fp2_laps.empty:
                fp_pace = calculate_clean_lap_pace(fp2_laps)
                team_data = fp_pace.get("teams", {}).get("Alpine") or fp_pace.get("teams", {}).get(
                    "BWT Alpine F1 Team"
                )
                if team_data and "delta_to_field_median" in team_data:
                    practice_pace_delta = float(team_data["delta_to_field_median"])

        qualifying_grid_pos = recent_avg_finish  # fallback default
        if stage in ["POST_QUALIFYING", "PRE_RACE"]:
            # Check target qualifying results
            session_id = f"{season}_{round_number:02d}_Q"
            q_res = self.db.get_session_results(session_id)
            driver_q = [r for r in q_res if r.get("driver_code") == driver_code]
            if driver_q and driver_q[0].get("grid_position"):
                qualifying_grid_pos = float(driver_q[0]["grid_position"])
            else:
                q_perf = calculate_qualifying_performance(q_res)
                if driver_code in q_perf.get("drivers", {}):
                    qualifying_grid_pos = float(
                        q_perf["drivers"][driver_code].get("grid_position", recent_avg_finish)
                    )

        features: dict[str, float] = {
            "recent_normalized_pace_delta": recent_pace_delta,
            "recent_avg_finish": recent_avg_finish,
            "recent_points_rate": recent_points_rate,
            "recent_reliability_rate": recent_reliability_rate,
            "season_avg_finish": season_avg_finish,
            "circuit_overtaking_difficulty": circuit_info["overtaking_difficulty"],
            "circuit_downforce_demand": circuit_info["downforce_demand"],
            "circuit_deg_severity": circuit_info["deg_severity"],
            "practice_pace_delta": practice_pace_delta,
            "qualifying_grid_pos": qualifying_grid_pos,
            "weather_rain_prob": float(weather_rain_prob),
        }

        return FeatureVector(
            season=season,
            round_number=round_number,
            stage=stage,
            target_event_id=target_event_id,
            driver_code=driver_code,
            feature_names=self.FEATURE_NAMES,
            features=features,
        )

    def _get_strictly_prior_races(
        self, season: int, round_number: int, constructor_id: str
    ) -> list[dict[str, Any]]:
        """Query historical races strictly before target event cutoff."""
        if not self.db:
            return []
        query = """
            SELECT
                e.season,
                e.round_number,
                e.event_name,
                r.driver_code,
                r.finish_position,
                r.points,
                r.finish_status
            FROM session_results r
            JOIN sessions s ON r.session_id = s.id
            JOIN events e ON s.event_id = e.id
            WHERE s.session_type = 'R'
              AND r.constructor_id = ?
              AND (
                  (e.season < ?)
                  OR (e.season = ? AND e.round_number < ?)
              )
            ORDER BY e.season ASC, e.round_number ASC;
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(
                query, (constructor_id, season, season, round_number)
            ).fetchall()
            return [dict(r) for r in rows]

    def _get_circuit_characteristics(self, event_name: str) -> dict[str, float]:
        """Look up circuit characteristics by keyword matching."""
        clean = event_name.lower()
        for key, vals in self.CIRCUIT_CHARACTERISTICS.items():
            if key in clean:
                return vals
        # Default medium-downforce, medium-overtaking circuit
        return {
            "overtaking_difficulty": 0.50,
            "downforce_demand": 0.50,
            "deg_severity": 0.50,
        }
