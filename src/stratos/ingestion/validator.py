"""Data validation and data coverage reporting for STRATOS.

Detects corrupted laps, negative tyre ages, improbable times, and missing fields.
Computes clean lap status (excluding pit in/out, safety cars, and pace outliers).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from stratos.storage.database import StratosDB
    from stratos.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

VALID_COMPOUNDS: set[str] = {
    "SOFT",
    "MEDIUM",
    "HARD",
    "INTERMEDIATE",
    "WET",
    "UNKNOWN",
}


class DataValidator:
    """Validates raw timing, telemetry, and classification records."""

    @staticmethod
    def _to_seconds(val: Any) -> float | None:
        """Convert pandas Timedelta or float to seconds."""
        if pd.isna(val) or val is None:
            return None
        if isinstance(val, pd.Timedelta):
            return float(val.total_seconds())
        try:
            sec = float(val)
            return sec if sec > 0 else None
        except (ValueError, TypeError):
            return None

    @classmethod
    def validate_laps(
        cls, df: pd.DataFrame, session_id: str
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        """Validate and clean a raw FastF1 laps DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Raw laps DataFrame from FastF1.
        session_id : str
            Identifier for logging warnings.

        Returns
        -------
        tuple[pd.DataFrame, list[dict[str, Any]]]
            Cleaned DataFrame with normalized columns and calculated `is_clean_lap`,
            plus a list of detected data quality warning dicts.
        """
        if df.empty:
            return df.copy(), []

        clean_df = df.copy()
        warnings: list[dict[str, Any]] = []

        # 1. Normalize column names
        col_rename = {
            "Driver": "driver",
            "DriverNumber": "driver_number",
            "Team": "team",
            "LapNumber": "lap_number",
            "LapTime": "lap_time_seconds",
            "Sector1Time": "sector_1_seconds",
            "Sector2Time": "sector_2_seconds",
            "Sector3Time": "sector_3_seconds",
            "SpeedI1": "speed_i1",
            "SpeedI2": "speed_i2",
            "SpeedFL": "speed_fl",
            "SpeedST": "speed_st",
            "Compound": "compound",
            "TyreLife": "tyre_life",
            "FreshTyre": "fresh_tyre",
            "Stint": "stint",
            "PitInTime": "pit_in_time",
            "PitOutTime": "pit_out_time",
            "TrackStatus": "track_status",
            "IsAccurate": "is_accurate",
        }
        for old_col, new_col in col_rename.items():
            if old_col in clean_df.columns and new_col not in clean_df.columns:
                clean_df[new_col] = clean_df[old_col]

        # 2. Convert Timedelta columns to seconds
        time_cols = [
            "lap_time_seconds",
            "sector_1_seconds",
            "sector_2_seconds",
            "sector_3_seconds",
        ]
        for time_col in time_cols:
            if time_col in clean_df.columns:
                clean_df[time_col] = clean_df[time_col].apply(cls._to_seconds)

        # 3. Validate lap times bounds
        if "lap_time_seconds" in clean_df.columns:
            invalid_laps = clean_df[
                clean_df["lap_time_seconds"].notna()
                & ((clean_df["lap_time_seconds"] < 40.0) | (clean_df["lap_time_seconds"] > 300.0))
            ]
            if not invalid_laps.empty:
                warnings.append(
                    {
                        "check_name": "LAP_TIME_BOUNDS",
                        "severity": "WARNING",
                        "field_name": "lap_time_seconds",
                        "message": (
                            f"Found {len(invalid_laps)} laps with abnormal lap times "
                            "(<40s or >300s)."
                        ),
                        "raw_value": str(invalid_laps["lap_time_seconds"].head(3).tolist()),
                    }
                )

        # 4. Normalize Compounds
        if "compound" in clean_df.columns:
            clean_df["compound"] = (
                clean_df["compound"].fillna("UNKNOWN").astype(str).str.upper().str.strip()
            )
            clean_df["compound"] = clean_df["compound"].apply(
                lambda c: c if c in VALID_COMPOUNDS else "UNKNOWN"
            )

        # 5. Validate Tyre Life
        if "tyre_life" in clean_df.columns:
            clean_df["tyre_life"] = pd.to_numeric(clean_df["tyre_life"], errors="coerce").fillna(0)
            negative_life = clean_df[clean_df["tyre_life"] < 0]
            if not negative_life.empty:
                clean_df.loc[clean_df["tyre_life"] < 0, "tyre_life"] = 0
                warnings.append(
                    {
                        "check_name": "NEGATIVE_TYRE_LIFE",
                        "severity": "ERROR",
                        "field_name": "tyre_life",
                        "message": (
                            f"Corrected {len(negative_life)} negative tyre life values to 0."
                        ),
                        "raw_value": str(negative_life["tyre_life"].head(3).tolist()),
                    }
                )

        # 6. Compute `is_clean_lap` (Clean-Lap Filter)
        # Criteria:
        # - Has valid lap time
        # - No Pit In / Pit Out
        # - Track status is '1' (All Clear; no SC/VSC/Yellow flag)
        # - Accurate flag from FastF1 is True (if available)
        is_clean = pd.Series(True, index=clean_df.index)

        if "lap_time_seconds" in clean_df.columns:
            is_clean &= clean_df["lap_time_seconds"].notna()
        else:
            is_clean &= False

        if "pit_in_time" in clean_df.columns:
            is_clean &= clean_df["pit_in_time"].isna()
        if "pit_out_time" in clean_df.columns:
            is_clean &= clean_df["pit_out_time"].isna()

        if "track_status" in clean_df.columns:
            # TrackStatus '1' is all clear
            clean_df["track_status"] = clean_df["track_status"].astype(str)
            is_clean &= clean_df["track_status"].isin(["1", "1.0", "nan"])

        if "is_accurate" in clean_df.columns:
            # If FastF1 explicitly marked lap as not accurate, exclude from clean laps
            is_clean &= clean_df["is_accurate"].fillna(True).astype(bool)

        clean_df["is_clean_lap"] = is_clean

        # Filter out 107% outliers per driver for clean pace calculations
        if "driver" in clean_df.columns and "lap_time_seconds" in clean_df.columns:
            for driver, driver_laps in clean_df[clean_df["is_clean_lap"]].groupby("driver"):
                median_pace = driver_laps["lap_time_seconds"].median()
                if not pd.isna(median_pace) and median_pace > 0:
                    cutoff = median_pace * 1.07
                    outlier_mask = (clean_df["driver"] == driver) & (
                        clean_df["lap_time_seconds"] > cutoff
                    )
                    clean_df.loc[outlier_mask, "is_clean_lap"] = False

        return clean_df, warnings

    @classmethod
    def validate_results(
        cls, results: list[dict[str, Any]], session_id: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Validate driver classification records."""
        cleaned: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        seen_drivers: set[str] = set()

        for r in results:
            driver = r.get("driver_code", "UNK")
            if driver in seen_drivers:
                warnings.append(
                    {
                        "check_name": "DUPLICATE_DRIVER_RESULT",
                        "severity": "WARNING",
                        "field_name": "driver_code",
                        "message": f"Duplicate driver classification entry for {driver}.",
                        "raw_value": driver,
                    }
                )
                continue
            seen_drivers.add(driver)

            # Ensure valid finish position
            fin_pos = r.get("finish_position")
            if fin_pos is not None:
                try:
                    fin_pos = int(fin_pos)
                    if fin_pos < 1 or fin_pos > 25:
                        warnings.append(
                            {
                                "check_name": "IMPROBABLE_FINISH_POSITION",
                                "severity": "WARNING",
                                "field_name": "finish_position",
                                "message": (
                                    f"Finish position {fin_pos} outside standard 1-25 range."
                                ),
                                "raw_value": str(fin_pos),
                            }
                        )
                except (ValueError, TypeError):
                    fin_pos = None

            # Ensure valid points
            pts = float(r.get("points", 0.0))
            if pts < 0:
                warnings.append(
                    {
                        "check_name": "NEGATIVE_POINTS",
                        "severity": "ERROR",
                        "field_name": "points",
                        "message": f"Negative championship points {pts} reset to 0.",
                        "raw_value": str(pts),
                    }
                )
                pts = 0.0

            r_clean = dict(r)
            r_clean["finish_position"] = fin_pos
            r_clean["points"] = pts
            cleaned.append(r_clean)

        return cleaned, warnings


class CoverageReporter:
    """Generates comprehensive data availability and audit reports."""

    @staticmethod
    def generate_report(
        db: StratosDB, parquet_store: ParquetStore | None = None
    ) -> dict[str, Any]:
        """Generate a structured coverage report of stored historical datasets.

        Parameters
        ----------
        db : StratosDB
            Database instance.
        parquet_store : ParquetStore or None
            Parquet store instance to audit files on disk.

        Returns
        -------
        dict[str, Any]
            Audited coverage report.
        """
        base_coverage = db.get_data_coverage()
        parquet_datasets = parquet_store.list_datasets() if parquet_store else []

        # Calculate total storage size
        total_parquet_bytes = sum(d["size_bytes"] for d in parquet_datasets)

        return {
            "seasons": base_coverage["seasons"],
            "total_results": base_coverage["total_results"],
            "total_predictions": base_coverage["total_predictions"],
            "last_successful_sync": base_coverage["last_successful_sync"],
            "parquet_files_count": len(parquet_datasets),
            "parquet_total_size_mb": round(total_parquet_bytes / (1024 * 1024), 2),
            "parquet_datasets": parquet_datasets,
        }
