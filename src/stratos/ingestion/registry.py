"""Data Source Registry and Provenance tracking for STRATOS.

Maintains registered external Formula 1 data sources and records cryptographic
provenance metadata for all ingested historical sessions.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stratos.storage.database import StratosDB

logger = logging.getLogger(__name__)


class DataSourceRegistry:
    """Manages the registry of official and documented F1 data sources."""

    SOURCES: list[dict[str, str]] = [
        {
            "id": "fastf1",
            "name": "FastF1 Python Library",
            "url": "https://docs.fastf1.dev/",
            "description": "Historical session timing, sectors, telemetry, tyre data, weather.",
            "documentation_url": "https://docs.fastf1.dev/",
        },
        {
            "id": "alpine_official",
            "name": "BWT Alpine F1 Team Media Centre",
            "url": "https://media.alpinecars.com/",
            "description": "Official Alpine team previews, reports, and driver statements.",
            "documentation_url": "https://www.alpinef1.com/",
        },
        {
            "id": "f1_official",
            "name": "Formula 1 Official Results Portal",
            "url": "https://www.formula1.com/en/results",
            "description": "Official race classifications, starting grids, and standings.",
            "documentation_url": "https://www.formula1.com/en/results",
        },
        {
            "id": "fia_official",
            "name": "FIA Official Regulations and Documents",
            "url": "https://www.fia.com/",
            "description": "Official sporting regulations, event classifications, and decisions.",
            "documentation_url": "https://www.fia.com/",
        },
    ]

    @classmethod
    def register_defaults(cls, db: StratosDB) -> None:
        """Seed the data_sources table with official data sources."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with db.get_connection() as conn:
            for src in cls.SOURCES:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO data_sources (
                        id, name, url, description, documentation_url, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        src["id"],
                        src["name"],
                        src["url"],
                        src["description"],
                        src["documentation_url"],
                        now,
                    ),
                )
            conn.commit()

    @staticmethod
    def compute_dataframe_checksum(df: Any) -> str:
        """Compute a deterministic SHA-256 hash of a pandas DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame to hash.

        Returns
        -------
        str
            Hexadecimal SHA-256 checksum string.
        """
        import pandas as pd

        if not isinstance(df, pd.DataFrame) or df.empty:
            return ""
        # Hash row representations
        raw_bytes = df.to_json(orient="records").encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    @classmethod
    def record_provenance(
        cls,
        db: StratosDB,
        dataset_key: str,
        source_id: str,
        season: int,
        record_count: int,
        event_id: str | None = None,
        session_id: str | None = None,
        data_availability: str = "COMPLETE",
        checksum: str = "",
        schema_version: str = "1.0.0",
    ) -> str:
        """Record provenance for an ingested dataset.

        Parameters
        ----------
        db : StratosDB
            Database instance.
        dataset_key : str
            Identifier for the dataset (e.g. 'laps_2024_01_R').
        source_id : str
            Identifier of registered source (e.g. 'fastf1').
        season : int
            Championship season.
        record_count : int
            Number of rows/records ingested.
        event_id : str or None
            Associated event ID.
        session_id : str or None
            Associated session ID.
        data_availability : str
            Availability status ('COMPLETE', 'PARTIAL', 'TELEMETRY_UNAVAILABLE').
        checksum : str
            Cryptographic SHA-256 digest of the dataset.
        schema_version : str
            Data contract version.

        Returns
        -------
        str
            Unique provenance ID.
        """
        prov_dict = {
            "id": f"prov_{dataset_key}",
            "dataset_key": dataset_key,
            "source_id": source_id,
            "season": season,
            "event_id": event_id,
            "session_id": session_id,
            "retrieval_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "schema_version": schema_version,
            "data_availability": data_availability,
            "record_count": record_count,
            "checksum": checksum,
        }
        return db.record_provenance(prov_dict)
