"""SQLite persistent storage manager for STRATOS Formula 1 intelligence.

Manages relational schema, events, sessions, results, predictions, experiment tracking,
provenance records, data quality warnings, transactions, and backups.
"""

from __future__ import annotations

import datetime
import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH: str = "data/stratos.db"
CURRENT_SCHEMA_VERSION: str = "1.0.0"


class StratosDB:
    """Thread-safe SQLite database manager for STRATOS.

    Handles creation and querying of tables for:
    - data_sources
    - events
    - sessions
    - session_results
    - pit_stops
    - race_control_events
    - source_provenance
    - ingestion_log
    - data_quality_warnings
    - predictions
    - experiments
    - metadata
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        """Initialize the database manager and ensure tables are created.

        Parameters
        ----------
        db_path : str or Path
            Path to the SQLite database file.
        """
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_connection()
        self.init_schema()

    def _init_connection(self) -> None:
        """Configure SQLite pragmas for performance and integrity."""
        with self.get_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Open, yield, and reliably close an SQLite connection with Row factory.

        Yields
        ------
        sqlite3.Connection
            Configured SQLite connection.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create all required tables, indices, and default provenance sources."""
        with self.get_connection() as conn:
            # 1. Data Sources Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS data_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    description TEXT,
                    documentation_url TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

            # 2. Grand Prix Events Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    season INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    event_name TEXT NOT NULL,
                    official_name TEXT,
                    country TEXT,
                    location TEXT,
                    event_date TEXT,
                    circuit_key TEXT,
                    is_sprint INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(season, round_number)
                );
                """
            )

            # 3. Sessions Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    season INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    session_type TEXT NOT NULL,
                    session_name TEXT NOT NULL,
                    session_date TEXT,
                    total_laps INTEGER DEFAULT 0,
                    total_drivers INTEGER DEFAULT 0,
                    has_laps INTEGER DEFAULT 0,
                    has_weather INTEGER DEFAULT 0,
                    has_telemetry INTEGER DEFAULT 0,
                    parquet_laps_path TEXT,
                    parquet_weather_path TEXT,
                    parquet_telemetry_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(season, round_number, session_type)
                );
                """
            )

            # 4. Session Results Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_results (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    driver_number TEXT,
                    driver_code TEXT NOT NULL,
                    driver_name TEXT NOT NULL,
                    constructor_id TEXT NOT NULL,
                    constructor_name TEXT NOT NULL,
                    grid_position INTEGER,
                    finish_position INTEGER,
                    classified_position TEXT,
                    points REAL DEFAULT 0.0,
                    finish_status TEXT,
                    q1_time REAL,
                    q2_time REAL,
                    q3_time REAL,
                    fastest_lap_time REAL,
                    fastest_lap_rank INTEGER,
                    total_time_seconds REAL,
                    UNIQUE(session_id, driver_code)
                );
                """
            )

            # 5. Pit Stops Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pit_stops (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    driver_code TEXT NOT NULL,
                    lap_number INTEGER NOT NULL,
                    stop_number INTEGER NOT NULL,
                    pit_duration REAL,
                    pit_lane_time REAL,
                    compound_in TEXT,
                    compound_out TEXT,
                    tyre_life_in INTEGER
                );
                """
            )

            # 6. Race Control Messages Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS race_control_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_number INTEGER,
                    timestamp TEXT,
                    category TEXT,
                    status TEXT,
                    message TEXT NOT NULL
                );
                """
            )

            # 7. Source Provenance Registry Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_provenance (
                    id TEXT PRIMARY KEY,
                    dataset_key TEXT NOT NULL,
                    source_id TEXT NOT NULL REFERENCES data_sources(id),
                    season INTEGER NOT NULL,
                    event_id TEXT,
                    session_id TEXT,
                    retrieval_timestamp TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    data_availability TEXT NOT NULL,
                    record_count INTEGER NOT NULL,
                    checksum TEXT
                );
                """
            )

            # 8. Ingestion Log Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    season INTEGER,
                    round_number INTEGER,
                    session_type TEXT,
                    status TEXT NOT NULL,
                    message TEXT,
                    records_ingested INTEGER DEFAULT 0,
                    duration_seconds REAL DEFAULT 0.0
                );
                """
            )

            # 9. Data Quality Warnings Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS data_quality_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT NOT NULL,
                    check_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    field_name TEXT,
                    message TEXT NOT NULL,
                    raw_value TEXT
                );
                """
            )

            # 10. Saved Predictions Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS predictions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    prediction_cutoff TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    target_event_id TEXT NOT NULL,
                    target_season INTEGER NOT NULL,
                    target_round INTEGER NOT NULL,
                    model_version TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    predicted_value REAL NOT NULL,
                    interval_low REAL,
                    interval_high REAL,
                    distribution_json TEXT,
                    feature_values_json TEXT,
                    assumptions TEXT,
                    actual_value REAL,
                    actual_recorded_at TEXT,
                    is_evaluated INTEGER DEFAULT 0,
                    error REAL
                );
                """
            )

            # 11. Experiments Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    config_json TEXT NOT NULL,
                    train_seasons_json TEXT,
                    test_seasons_json TEXT,
                    metrics_json TEXT NOT NULL,
                    baseline_metrics_json TEXT,
                    is_reproducible INTEGER DEFAULT 1
                );
                """
            )

            # 12. Metadata Table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

            # Indices for performant querying
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_season ON events(season);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_season ON sessions(season);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_event ON sessions(event_id);")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_constructor "
                "ON session_results(constructor_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_driver "
                "ON session_results(driver_code);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_predictions_target "
                "ON predictions(target_event_id, stage);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_warnings_session "
                "ON data_quality_warnings(session_id);"
            )

            # Seed default authentic data sources
            now = datetime.datetime.now(datetime.UTC).isoformat()
            default_sources = [
                (
                    "fastf1",
                    "FastF1 Python Library",
                    "https://docs.fastf1.dev/",
                    "Official timing, sector, car telemetry, tyre compounds, and weather data.",
                    "https://docs.fastf1.dev/",
                    now,
                ),
                (
                    "alpine_official",
                    "BWT Alpine F1 Team Official",
                    "https://www.alpinef1.com/",
                    "Official Alpine race reports, technical previews, and driver statements.",
                    "https://media.alpinecars.com/",
                    now,
                ),
                (
                    "f1_official",
                    "Formula 1 Official Results",
                    "https://www.formula1.com/en/results",
                    "Published race classifications, starting grids, and championship standings.",
                    "https://www.formula1.com/en/results",
                    now,
                ),
                (
                    "fia_official",
                    "FIA Official Documents",
                    "https://www.fia.com/",
                    "Official sporting regulations, event classifications, and stewards decisions.",
                    "https://www.fia.com/",
                    now,
                ),
            ]
            conn.executemany(
                """
                INSERT OR IGNORE INTO data_sources (
                    id, name, url, description, documentation_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                default_sources,
            )

            # Record schema version metadata
            conn.execute(
                """
                INSERT OR REPLACE INTO metadata (key, value, updated_at)
                VALUES ('schema_version', ?, ?);
                """,
                (CURRENT_SCHEMA_VERSION, now),
            )
            conn.commit()

    # -------------------------------------------------------------------------
    # Events & Sessions CRUD
    # -------------------------------------------------------------------------

    def upsert_event(self, event: dict[str, Any]) -> str:
        """Insert or update a Grand Prix event.

        Parameters
        ----------
        event : dict[str, Any]
            Event dictionary containing season, round_number, event_name, etc.

        Returns
        -------
        str
            The event ID.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        season = int(event["season"])
        round_num = int(event["round_number"])
        event_id = event.get("id") or f"{season}_{round_num:02d}_{event['event_name'][:3].upper()}"

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    id, season, round_number, event_name, official_name,
                    country, location, event_date, circuit_key, is_sprint,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(season, round_number) DO UPDATE SET
                    event_name = excluded.event_name,
                    official_name = excluded.official_name,
                    country = excluded.country,
                    location = excluded.location,
                    event_date = excluded.event_date,
                    circuit_key = excluded.circuit_key,
                    is_sprint = excluded.is_sprint,
                    updated_at = excluded.updated_at;
                """,
                (
                    event_id,
                    season,
                    round_num,
                    event["event_name"],
                    event.get("official_name", event["event_name"]),
                    event.get("country", ""),
                    event.get("location", ""),
                    str(event.get("event_date", "")),
                    event.get("circuit_key", ""),
                    1 if event.get("is_sprint") else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
        return event_id

    def upsert_session(self, session: dict[str, Any]) -> str:
        """Insert or update a session record.

        Parameters
        ----------
        session : dict[str, Any]
            Session dictionary containing event_id, session_type, etc.

        Returns
        -------
        str
            The session ID.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        season = int(session["season"])
        round_num = int(session["round_number"])
        session_type = session["session_type"]
        session_id = session.get("id") or f"{season}_{round_num:02d}_{session_type}"

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, event_id, season, round_number, session_type, session_name,
                    session_date, total_laps, total_drivers, has_laps, has_weather,
                    has_telemetry, parquet_laps_path, parquet_weather_path,
                    parquet_telemetry_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(season, round_number, session_type) DO UPDATE SET
                    total_laps = excluded.total_laps,
                    total_drivers = excluded.total_drivers,
                    has_laps = excluded.has_laps,
                    has_weather = excluded.has_weather,
                    has_telemetry = excluded.has_telemetry,
                    parquet_laps_path = excluded.parquet_laps_path,
                    parquet_weather_path = excluded.parquet_weather_path,
                    parquet_telemetry_path = excluded.parquet_telemetry_path,
                    updated_at = excluded.updated_at;
                """,
                (
                    session_id,
                    session["event_id"],
                    season,
                    round_num,
                    session_type,
                    session.get("session_name", session_type),
                    str(session.get("session_date", "")),
                    int(session.get("total_laps", 0)),
                    int(session.get("total_drivers", 0)),
                    1 if session.get("has_laps") else 0,
                    1 if session.get("has_weather") else 0,
                    1 if session.get("has_telemetry") else 0,
                    str(session.get("parquet_laps_path", "")),
                    str(session.get("parquet_weather_path", "")),
                    str(session.get("parquet_telemetry_path", "")),
                    now,
                    now,
                ),
            )
            conn.commit()
        return session_id

    def save_session_results(self, session_id: str, results: list[dict[str, Any]]) -> int:
        """Insert or replace driver classification records for a session.

        Parameters
        ----------
        session_id : str
            The session identifier.
        results : list[dict[str, Any]]
            List of result dictionaries.

        Returns
        -------
        int
            Number of rows saved.
        """
        with self.get_connection() as conn:
            for r in results:
                result_id = f"{session_id}_{r['driver_code']}"
                conn.execute(
                    """
                    INSERT INTO session_results (
                        id, session_id, driver_number, driver_code, driver_name,
                        constructor_id, constructor_name, grid_position, finish_position,
                        classified_position, points, finish_status, q1_time, q2_time,
                        q3_time, fastest_lap_time, fastest_lap_rank, total_time_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, driver_code) DO UPDATE SET
                        driver_number = excluded.driver_number,
                        driver_name = excluded.driver_name,
                        constructor_id = excluded.constructor_id,
                        constructor_name = excluded.constructor_name,
                        grid_position = excluded.grid_position,
                        finish_position = excluded.finish_position,
                        classified_position = excluded.classified_position,
                        points = excluded.points,
                        finish_status = excluded.finish_status,
                        q1_time = excluded.q1_time,
                        q2_time = excluded.q2_time,
                        q3_time = excluded.q3_time,
                        fastest_lap_time = excluded.fastest_lap_time,
                        fastest_lap_rank = excluded.fastest_lap_rank,
                        total_time_seconds = excluded.total_time_seconds;
                    """,
                    (
                        result_id,
                        session_id,
                        str(r.get("driver_number", "")),
                        r["driver_code"],
                        r["driver_name"],
                        r["constructor_id"],
                        r["constructor_name"],
                        r.get("grid_position"),
                        r.get("finish_position"),
                        str(r.get("classified_position", "")),
                        float(r.get("points", 0.0)),
                        r.get("finish_status", "Finished"),
                        r.get("q1_time"),
                        r.get("q2_time"),
                        r.get("q3_time"),
                        r.get("fastest_lap_time"),
                        r.get("fastest_lap_rank"),
                        r.get("total_time_seconds"),
                    ),
                )
            conn.commit()
        return len(results)

    def save_pit_stops(self, session_id: str, pit_stops: list[dict[str, Any]]) -> int:
        """Save pit stops for a session.

        Parameters
        ----------
        session_id : str
            The session identifier.
        pit_stops : list[dict[str, Any]]
            List of pit stop records.

        Returns
        -------
        int
            Number of rows saved.
        """
        with self.get_connection() as conn:
            for ps in pit_stops:
                stop_id = (
                    f"{session_id}_{ps['driver_code']}_{ps['lap_number']}_{ps['stop_number']}"
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pit_stops (
                        id, session_id, driver_code, lap_number, stop_number,
                        pit_duration, pit_lane_time, compound_in, compound_out, tyre_life_in
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        stop_id,
                        session_id,
                        ps["driver_code"],
                        int(ps["lap_number"]),
                        int(ps["stop_number"]),
                        ps.get("pit_duration"),
                        ps.get("pit_lane_time"),
                        ps.get("compound_in"),
                        ps.get("compound_out"),
                        ps.get("tyre_life_in"),
                    ),
                )
            conn.commit()
        return len(pit_stops)

    def save_race_control_events(
        self, session_id: str, events: list[dict[str, Any]]
    ) -> int:
        """Save race control safety car, VSC, and flag events.

        Parameters
        ----------
        session_id : str
            The session identifier.
        events : list[dict[str, Any]]
            List of race control event dictionaries.

        Returns
        -------
        int
            Number of rows saved.
        """
        with self.get_connection() as conn:
            for idx, ev in enumerate(events):
                event_id = f"{session_id}_rc_{idx}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO race_control_events (
                        id, session_id, lap_number, timestamp, category, status, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        event_id,
                        session_id,
                        ev.get("lap_number"),
                        str(ev.get("timestamp", "")),
                        ev.get("category", "General"),
                        ev.get("status", ""),
                        ev["message"],
                    ),
                )
            conn.commit()
        return len(events)

    # -------------------------------------------------------------------------
    # Provenance, Logs, and Data Quality
    # -------------------------------------------------------------------------

    def record_provenance(self, prov: dict[str, Any]) -> str:
        """Record provenance for an ingested dataset.

        Parameters
        ----------
        prov : dict[str, Any]
            Provenance attributes.

        Returns
        -------
        str
            The provenance ID.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        prov_id = prov.get("id") or f"prov_{prov['dataset_key']}_{prov['season']}"
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO source_provenance (
                    id, dataset_key, source_id, season, event_id, session_id,
                    retrieval_timestamp, schema_version, data_availability, record_count, checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    prov_id,
                    prov["dataset_key"],
                    prov.get("source_id", "fastf1"),
                    int(prov["season"]),
                    prov.get("event_id"),
                    prov.get("session_id"),
                    prov.get("retrieval_timestamp", now),
                    prov.get("schema_version", CURRENT_SCHEMA_VERSION),
                    prov.get("data_availability", "COMPLETE"),
                    int(prov.get("record_count", 0)),
                    prov.get("checksum", ""),
                ),
            )
            conn.commit()
        return prov_id

    def log_ingestion(
        self,
        status: str,
        message: str,
        season: int | None = None,
        round_number: int | None = None,
        session_type: str | None = None,
        records_ingested: int = 0,
        duration_seconds: float = 0.0,
    ) -> int:
        """Write an entry to the ingestion log.

        Returns
        -------
        int
            Row ID of the created log entry.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ingestion_log (
                    timestamp, season, round_number, session_type, status,
                    message, records_ingested, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    now,
                    season,
                    round_number,
                    session_type,
                    status.upper(),
                    message,
                    records_ingested,
                    duration_seconds,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def log_data_warning(
        self,
        check_name: str,
        severity: str,
        message: str,
        session_id: str | None = None,
        field_name: str | None = None,
        raw_value: str | None = None,
    ) -> int:
        """Record a data-quality anomaly or missing-data flag.

        Returns
        -------
        int
            Row ID of the warning entry.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO data_quality_warnings (
                    session_id, timestamp, check_name, severity,
                    field_name, message, raw_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    now,
                    check_name,
                    severity.upper(),
                    field_name,
                    message,
                    str(raw_value) if raw_value is not None else None,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    # -------------------------------------------------------------------------
    # Predictions and Experiments
    # -------------------------------------------------------------------------

    def save_prediction(self, pred: dict[str, Any]) -> str:
        """Save a model prediction run without overwriting historical forecasts.

        Parameters
        ----------
        pred : dict[str, Any]
            Prediction parameters and distributions.

        Returns
        -------
        str
            The unique prediction ID.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        pred_id = pred.get("id") or (
            f"pred_{pred['target_event_id']}_{pred['stage']}_"
            f"{pred['target_type']}_{int(datetime.datetime.now().timestamp())}"
        )
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO predictions (
                    id, created_at, prediction_cutoff, stage, target_event_id,
                    target_season, target_round, model_version, target_type,
                    predicted_value, interval_low, interval_high, distribution_json,
                    feature_values_json, assumptions, actual_value, actual_recorded_at,
                    is_evaluated, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    pred_id,
                    pred.get("created_at", now),
                    pred["prediction_cutoff"],
                    pred["stage"],
                    pred["target_event_id"],
                    int(pred["target_season"]),
                    int(pred["target_round"]),
                    pred["model_version"],
                    pred["target_type"],
                    float(pred["predicted_value"]),
                    pred.get("interval_low"),
                    pred.get("interval_high"),
                    (
                        json.dumps(pred["distribution"])
                        if isinstance(pred.get("distribution"), dict | list)
                        else pred.get("distribution_json")
                    ),
                    (
                        json.dumps(pred["feature_values"])
                        if isinstance(pred.get("feature_values"), dict)
                        else pred.get("feature_values_json")
                    ),
                    pred.get("assumptions", ""),
                    pred.get("actual_value"),
                    pred.get("actual_recorded_at"),
                    1 if pred.get("is_evaluated") else 0,
                    pred.get("error"),
                ),
            )
            conn.commit()
        return pred_id

    def get_predictions(
        self,
        target_event_id: str | None = None,
        stage: str | None = None,
        model_version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve historical predictions with optional filters."""
        query = "SELECT * FROM predictions WHERE 1=1"
        params: list[Any] = []
        if target_event_id:
            query += " AND target_event_id = ?"
            params.append(target_event_id)
        if stage:
            query += " AND stage = ?"
            params.append(stage)
        if model_version:
            query += " AND model_version = ?"
            params.append(model_version)
        query += " ORDER BY created_at DESC;"

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def record_actual_outcome(
        self, prediction_id: str, actual_value: float
    ) -> None:
        """Update a saved forecast with its observed actual result and compute error."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT predicted_value FROM predictions WHERE id = ?;",
                (prediction_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Prediction with id '{prediction_id}' not found.")

            pred_val = float(row["predicted_value"])
            error = actual_value - pred_val
            conn.execute(
                """
                UPDATE predictions SET
                    actual_value = ?,
                    actual_recorded_at = ?,
                    is_evaluated = 1,
                    error = ?
                WHERE id = ?;
                """,
                (actual_value, now, error, prediction_id),
            )
            conn.commit()

    def save_experiment(self, exp: dict[str, Any]) -> str:
        """Save a research experiment run for reproducible benchmarking."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        exp_id = exp.get("id") or f"exp_{int(datetime.datetime.now().timestamp())}"
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiments (
                    id, created_at, name, description, config_json,
                    train_seasons_json, test_seasons_json, metrics_json,
                    baseline_metrics_json, is_reproducible
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    exp_id,
                    exp.get("created_at", now),
                    exp["name"],
                    exp.get("description", ""),
                    (
                        json.dumps(exp["config"])
                        if isinstance(exp.get("config"), dict)
                        else exp.get("config_json", "{}")
                    ),
                    (
                        json.dumps(exp["train_seasons"])
                        if isinstance(exp.get("train_seasons"), list)
                        else exp.get("train_seasons_json", "[]")
                    ),
                    (
                        json.dumps(exp["test_seasons"])
                        if isinstance(exp.get("test_seasons"), list)
                        else exp.get("test_seasons_json", "[]")
                    ),
                    (
                        json.dumps(exp["metrics"])
                        if isinstance(exp.get("metrics"), dict)
                        else exp.get("metrics_json", "{}")
                    ),
                    (
                        json.dumps(exp["baseline_metrics"])
                        if isinstance(exp.get("baseline_metrics"), dict)
                        else exp.get("baseline_metrics_json")
                    ),
                    1 if exp.get("is_reproducible", True) else 0,
                ),
            )
            conn.commit()
        return exp_id

    def get_experiments(self) -> list[dict[str, Any]]:
        """Retrieve all experiment records."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC;"
            ).fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # Queries, Coverage, and Export
    # -------------------------------------------------------------------------

    def query_races(
        self, season: int | None = None, constructor_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Query race classifications with optional season and constructor filters."""
        query = """
            SELECT
                e.season,
                e.round_number,
                e.event_name,
                e.country,
                e.event_date,
                s.session_type,
                r.driver_code,
                r.driver_name,
                r.constructor_id,
                r.constructor_name,
                r.grid_position,
                r.finish_position,
                r.points,
                r.finish_status,
                r.fastest_lap_time
            FROM session_results r
            JOIN sessions s ON r.session_id = s.id
            JOIN events e ON s.event_id = e.id
            WHERE s.session_type = 'R'
        """
        params: list[Any] = []
        if season is not None:
            query += " AND e.season = ?"
            params.append(season)
        if constructor_id is not None:
            query += " AND r.constructor_id = ?"
            params.append(constructor_id)
        query += " ORDER BY e.season DESC, e.round_number ASC, r.finish_position ASC;"

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_events(self, season: int | None = None) -> list[dict[str, Any]]:
        """Retrieve events with optional season filtering.

        Parameters
        ----------
        season : int, optional
            Season year to filter events.

        Returns
        -------
        list[dict[str, Any]]
            List of event dictionaries ordered chronologically.
        """
        query = "SELECT * FROM events"
        params: list[Any] = []
        if season is not None:
            query += " WHERE season = ?"
            params.append(season)
        query += " ORDER BY season ASC, round_number ASC;"

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_sessions(
        self, season: int | None = None, event_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve sessions with optional season and event filters.

        Parameters
        ----------
        season : int, optional
            Season year filter.
        event_id : str, optional
            Event identifier filter.

        Returns
        -------
        list[dict[str, Any]]
            List of session dictionaries.
        """
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list[Any] = []
        if season is not None:
            query += " AND season = ?"
            params.append(season)
        if event_id is not None:
            query += " AND event_id = ?"
            params.append(event_id)
        query += " ORDER BY season ASC, round_number ASC, session_date ASC;"

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_data_sources(self) -> list[dict[str, Any]]:
        """Retrieve all data sources registered in the database."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM data_sources ORDER BY id ASC;"
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["source_id"] = d.get("id", "")
                result.append(d)
            return result

    def get_session_results(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieve all driver classifications for a specific session."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM session_results
                WHERE session_id = ?
                ORDER BY
                    CASE WHEN finish_position IS NULL THEN 999 ELSE finish_position END ASC;
                """,
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_data_coverage(self) -> dict[str, Any]:
        """Generate a data coverage summary across all ingested seasons."""
        with self.get_connection() as conn:
            season_rows = conn.execute(
                """
                SELECT
                    season,
                    COUNT(DISTINCT id) as total_events,
                    SUM(is_sprint) as sprint_events
                FROM events
                GROUP BY season
                ORDER BY season DESC;
                """
            ).fetchall()

            session_rows = conn.execute(
                """
                SELECT
                    season,
                    COUNT(*) as total_sessions,
                    SUM(has_laps) as laps_count,
                    SUM(has_weather) as weather_count,
                    SUM(has_telemetry) as telemetry_count
                FROM sessions
                GROUP BY season
                ORDER BY season DESC;
                """
            ).fetchall()

            total_results = conn.execute(
                "SELECT COUNT(*) as cnt FROM session_results;"
            ).fetchone()["cnt"]

            total_predictions = conn.execute(
                "SELECT COUNT(*) as cnt FROM predictions;"
            ).fetchone()["cnt"]

            last_sync = self.get_metadata("last_successful_sync", "Never")

            seasons_summary = []
            session_map = {row["season"]: dict(row) for row in session_rows}
            for e_row in season_rows:
                s_data = session_map.get(e_row["season"], {})
                seasons_summary.append(
                    {
                        "season": e_row["season"],
                        "events": e_row["total_events"],
                        "sprints": e_row["sprint_events"],
                        "sessions": s_data.get("total_sessions", 0),
                        "laps_loaded": s_data.get("laps_count", 0),
                        "weather_loaded": s_data.get("weather_count", 0),
                        "telemetry_loaded": s_data.get("telemetry_count", 0),
                    }
                )

            return {
                "seasons": seasons_summary,
                "total_results": total_results,
                "total_predictions": total_predictions,
                "last_successful_sync": last_sync,
            }

    def get_data_warnings(
        self, session_id: str | None = None, min_severity: str | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve logged data-quality warnings."""
        query = "SELECT * FROM data_quality_warnings WHERE 1=1"
        params: list[Any] = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if min_severity:
            query += " AND severity = ?"
            params.append(min_severity.upper())
        query += " ORDER BY id DESC LIMIT 500;"

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def set_metadata(self, key: str, value: str) -> None:
        """Store or update a key-value pair in metadata."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO metadata (key, value, updated_at)
                VALUES (?, ?, ?);
                """,
                (key, str(value), now),
            )
            conn.commit()

    def get_metadata(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a metadata value by key."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = ?;", (key,)
            ).fetchone()
            return row["value"] if row else default

    def export_to_csv(
        self,
        table_name: str,
        output_path: str | Path,
        where_clause: str = "",
        params: tuple[Any, ...] = (),
    ) -> Path:
        """Export any table to CSV file.

        Parameters
        ----------
        table_name : str
            Table name to export.
        output_path : str or Path
            Target CSV path.
        where_clause : str, optional
            SQL WHERE filter clause.
        params : tuple, optional
            Query parameters.

        Returns
        -------
        Path
            Path to written CSV file.
        """
        import pandas as pd

        allowed_tables = {
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
            "data_sources",
        }
        if table_name not in allowed_tables:
            raise ValueError(
                f"Invalid table '{table_name}'. Must be one of: {sorted(allowed_tables)}"
            )

        sql = f"SELECT * FROM {table_name}"  # noqa: S608
        if where_clause.strip():
            sql += f" WHERE {where_clause}"

        with self.get_connection() as conn:
            df = pd.read_sql_query(sql, conn, params=params)

        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        return out_path

    def export_table_to_csv(
        self,
        table_name: str,
        where_clause: str = "",
        params: tuple[Any, ...] = (),
    ) -> str:
        """Export any table to CSV string format for interactive download.

        Parameters
        ----------
        table_name : str
            Table name to export.
        where_clause : str, optional
            SQL WHERE filter clause.
        params : tuple, optional
            Query parameters.

        Returns
        -------
        str
            CSV formatted text.
        """
        import pandas as pd

        allowed_tables = {
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
            "data_sources",
        }
        if table_name not in allowed_tables:
            raise ValueError(
                f"Invalid table '{table_name}'. Must be one of: {sorted(allowed_tables)}"
            )

        sql = f"SELECT * FROM {table_name}"  # noqa: S608
        if where_clause.strip():
            sql += f" WHERE {where_clause}"

        with self.get_connection() as conn:
            df = pd.read_sql_query(sql, conn, params=params)

        return df.to_csv(index=False)

    def create_backup(self, backup_dir: str | Path = "data/backups") -> Path:
        """Create an online timestamped atomic backup of the SQLite database.

        Parameters
        ----------
        backup_dir : str or Path
            Directory where backup copies are stored, or direct backup file path.

        Returns
        -------
        Path
            Path to the created backup database file.
        """
        target = Path(backup_dir).resolve()
        if target.suffix == ".db":
            target.parent.mkdir(parents=True, exist_ok=True)
            backup_path = target
        else:
            target.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = target / f"stratos_backup_{timestamp}.db"

        with self.get_connection() as src_conn:
            dst_conn = sqlite3.connect(str(backup_path))
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()

        logger.info("Created SQLite database backup at: %s", backup_path)
        return backup_path
