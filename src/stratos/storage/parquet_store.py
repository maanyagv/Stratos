"""Parquet columnar storage manager for STRATOS processed telemetry and laps.

Provides high-efficiency storage and retrieval for session lap-by-lap records,
weather condition streams, and high-frequency car telemetry using Apache Parquet.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_PROCESSED_DIR: str = "data/processed"


class ParquetStore:
    """Manages processed datasets stored as Parquet files on disk."""

    def __init__(self, root_dir: str | Path = DEFAULT_PROCESSED_DIR) -> None:
        """Initialize Parquet store with root directory.

        Parameters
        ----------
        root_dir : str or Path
            Root directory where processed parquet datasets are stored.
        """
        self.root_dir = Path(root_dir).resolve()
        self.laps_dir = self.root_dir / "laps"
        self.weather_dir = self.root_dir / "weather"
        self.telemetry_dir = self.root_dir / "telemetry"

        for directory in [self.laps_dir, self.weather_dir, self.telemetry_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _file_stem(self, season: int, round_num: int, session_type: str) -> str:
        """Generate consistent filename stem."""
        return f"{season}_{round_num:02d}_{session_type.upper()}"

    # -------------------------------------------------------------------------
    # Laps
    # -------------------------------------------------------------------------

    def get_laps_path(self, season: int, round_num: int, session_type: str) -> Path:
        """Return the target parquet file path for lap times."""
        stem = self._file_stem(season, round_num, session_type)
        return self.laps_dir / f"{stem}.parquet"

    def has_laps(self, season: int, round_num: int, session_type: str) -> bool:
        """Check if processed laps file exists."""
        return self.get_laps_path(season, round_num, session_type).is_file()

    def save_laps(
        self,
        season: int,
        round_num: int,
        session_type: str,
        df: pd.DataFrame,
    ) -> Path:
        """Save processed laps dataframe to Parquet.

        Parameters
        ----------
        season : int
            Championship year.
        round_num : int
            Round number.
        session_type : str
            Session code ('R', 'Q', 'FP1', etc.).
        df : pd.DataFrame
            Lap records DataFrame.

        Returns
        -------
        Path
            Path to written parquet file.
        """
        out_path = self.get_laps_path(season, round_num, session_type)
        # Store categorical string columns efficiently
        clean_df = df.copy()
        for col in ["Driver", "Team", "Compound"]:
            if col in clean_df.columns:
                clean_df[col] = clean_df[col].astype(str)

        clean_df.to_parquet(out_path, index=False, engine="pyarrow", compression="snappy")
        logger.debug("Saved %d lap records to: %s", len(clean_df), out_path)
        return out_path

    def load_laps(
        self, season: int, round_num: int, session_type: str
    ) -> pd.DataFrame:
        """Load processed laps dataframe from Parquet.

        Returns
        -------
        pd.DataFrame
            Loaded lap records, or empty DataFrame if not found.
        """
        path = self.get_laps_path(season, round_num, session_type)
        if not path.is_file():
            return pd.DataFrame()
        return pd.read_parquet(path, engine="pyarrow")

    # -------------------------------------------------------------------------
    # Weather
    # -------------------------------------------------------------------------

    def get_weather_path(self, season: int, round_num: int, session_type: str) -> Path:
        """Return the target parquet file path for weather series."""
        stem = self._file_stem(season, round_num, session_type)
        return self.weather_dir / f"{stem}.parquet"

    def has_weather(self, season: int, round_num: int, session_type: str) -> bool:
        """Check if processed weather file exists."""
        return self.get_weather_path(season, round_num, session_type).is_file()

    def save_weather(
        self,
        season: int,
        round_num: int,
        session_type: str,
        df: pd.DataFrame,
    ) -> Path:
        """Save weather observations to Parquet."""
        out_path = self.get_weather_path(season, round_num, session_type)
        df.to_parquet(out_path, index=False, engine="pyarrow", compression="snappy")
        logger.debug("Saved %d weather samples to: %s", len(df), out_path)
        return out_path

    def load_weather(
        self, season: int, round_num: int, session_type: str
    ) -> pd.DataFrame:
        """Load weather observations from Parquet."""
        path = self.get_weather_path(season, round_num, session_type)
        if not path.is_file():
            return pd.DataFrame()
        return pd.read_parquet(path, engine="pyarrow")

    # -------------------------------------------------------------------------
    # Telemetry
    # -------------------------------------------------------------------------

    def get_telemetry_path(self, season: int, round_num: int, session_type: str) -> Path:
        """Return the target parquet file path for high-frequency telemetry."""
        stem = self._file_stem(season, round_num, session_type)
        return self.telemetry_dir / f"{stem}.parquet"

    def has_telemetry(self, season: int, round_num: int, session_type: str) -> bool:
        """Check if telemetry file exists."""
        return self.get_telemetry_path(season, round_num, session_type).is_file()

    def save_telemetry(
        self,
        season: int,
        round_num: int,
        session_type: str,
        df: pd.DataFrame,
    ) -> Path:
        """Save high-frequency telemetry samples to Parquet."""
        out_path = self.get_telemetry_path(season, round_num, session_type)
        df.to_parquet(out_path, index=False, engine="pyarrow", compression="snappy")
        logger.debug("Saved %d telemetry records to: %s", len(df), out_path)
        return out_path

    def load_telemetry(
        self, season: int, round_num: int, session_type: str
    ) -> pd.DataFrame:
        """Load telemetry samples from Parquet."""
        path = self.get_telemetry_path(season, round_num, session_type)
        if not path.is_file():
            return pd.DataFrame()
        return pd.read_parquet(path, engine="pyarrow")

    # -------------------------------------------------------------------------
    # Dataset Exploration
    # -------------------------------------------------------------------------

    def list_datasets(self) -> list[dict[str, Any]]:
        """List all available parquet datasets with file metadata."""
        datasets = []
        for file in self.laps_dir.glob("*.parquet"):
            parts = file.stem.split("_")
            if len(parts) >= 3:
                try:
                    season = int(parts[0])
                    round_num = int(parts[1])
                    session_type = parts[2]
                    stat = file.stat()
                    datasets.append(
                        {
                            "type": "laps",
                            "season": season,
                            "round_number": round_num,
                            "session_type": session_type,
                            "filename": file.name,
                            "size_bytes": stat.st_size,
                            "path": str(file),
                        }
                    )
                except ValueError:
                    continue
        return sorted(datasets, key=lambda d: (d["season"], d["round_number"]), reverse=True)
