"""Historical Formula 1 data ingestion pipeline for STRATOS.

Extracts official timing, telemetry, weather, and race control events from FastF1,
validates incoming data, records provenance, and persists to SQLite and Parquet.
"""

from __future__ import annotations

import datetime
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fastf1
import pandas as pd

from stratos.alpine.identity import map_constructor, map_driver
from stratos.data.loader import configure_cache, load_session
from stratos.ingestion.registry import DataSourceRegistry
from stratos.ingestion.validator import DataValidator
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary result of a session ingestion attempt."""

    season: int
    round_number: int
    session_type: str
    status: str  # 'SUCCESS', 'SKIPPED', 'WARNING', 'FAILED'
    records_ingested: int
    duration_seconds: float
    message: str
    warnings_count: int = 0


class IngestionPipeline:
    """Orchestrates reliable, incremental historical F1 session data ingestion."""

    def __init__(
        self,
        db: StratosDB | None = None,
        parquet_store: ParquetStore | None = None,
        cache_dir: str | Path = "data/cache",
    ) -> None:
        """Initialize the ingestion pipeline.

        Parameters
        ----------
        db : StratosDB or None
            Target relational database. If None, initializes default StratosDB.
        parquet_store : ParquetStore or None
            Target parquet store. If None, initializes default ParquetStore.
        cache_dir : str or Path
            Local FastF1 cache directory.
        """
        self.db = db if db is not None else StratosDB()
        self.parquet_store = (
            parquet_store if parquet_store is not None else ParquetStore()
        )
        self.cache_dir = Path(cache_dir).resolve()
        configure_cache(self.cache_dir)
        DataSourceRegistry.register_defaults(self.db)

    def ingest_event_schedule(self, season: int) -> list[dict[str, Any]]:
        """Fetch and persist the official Grand Prix calendar for a season.

        Parameters
        ----------
        season : int
            Championship year (2018–2026).

        Returns
        -------
        list[dict[str, Any]]
            List of saved event records.
        """
        logger.info("Fetching calendar schedule for season %d...", season)
        try:
            schedule = fastf1.get_event_schedule(season)
        except Exception as exc:
            logger.warning("Could not retrieve FastF1 schedule for season %d: %s", season, exc)
            return []

        saved_events: list[dict[str, Any]] = []
        for _, row in schedule.iterrows():
            round_num = row.get("RoundNumber")
            if pd.isna(round_num) or int(round_num) < 1:
                continue

            round_int = int(round_num)
            event_name = str(row.get("EventName", f"Round {round_int}"))
            official_name = str(row.get("OfficialEventName", event_name))
            country = str(row.get("Country", ""))
            location = str(row.get("Location", ""))
            event_date = str(row.get("EventDate", ""))
            event_format = str(row.get("EventFormat", "conventional"))
            is_sprint = "sprint" in event_format.lower()

            event_dict = {
                "season": season,
                "round_number": round_int,
                "event_name": event_name,
                "official_name": official_name,
                "country": country,
                "location": location,
                "event_date": event_date,
                "is_sprint": is_sprint,
            }
            self.db.upsert_event(event_dict)
            saved_events.append(event_dict)

        logger.info("Successfully persisted %d events for season %d.", len(saved_events), season)
        return saved_events

    def ingest_session(
        self,
        season: int,
        round_number: int,
        session_type: str = "R",
        force: bool = False,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> IngestionResult:
        """Ingest a single session with results, laps, weather, and race control messages.

        Parameters
        ----------
        season : int
            Championship season.
        round_number : int
            Round number in championship.
        session_type : str, default 'R'
            Session code ('R', 'Q', 'FP1', etc.).
        force : bool, default False
            If True, re-downloads and overwrites existing records.
        progress_callback : callable, optional
            Callback taking (status_message, progress_fraction).

        Returns
        -------
        IngestionResult
            Structured result summary of the ingestion attempt.
        """
        start_time = time.time()
        session_id = f"{season}_{round_number:02d}_{session_type}"

        def update_progress(msg: str, frac: float) -> None:
            if progress_callback:
                progress_callback(msg, frac)

        update_progress(f"Checking session {session_id}...", 0.05)

        # 1. Duplicate Detection / Incremental Check
        if not force:
            with self.db.get_connection() as conn:
                existing = conn.execute(
                    "SELECT id, has_laps FROM sessions WHERE id = ?;", (session_id,)
                ).fetchone()
                if existing and existing["has_laps"]:
                    msg = f"Session '{session_id}' already ingested. Skipping (force=False)."
                    logger.info(msg)
                    update_progress(msg, 1.0)
                    return IngestionResult(
                        season=season,
                        round_number=round_number,
                        session_type=session_type,
                        status="SKIPPED",
                        records_ingested=0,
                        duration_seconds=round(time.time() - start_time, 2),
                        message=msg,
                    )

        # 2. Acquire Session Data from FastF1
        update_progress(f"Loading session {session_id} from FastF1...", 0.20)
        try:
            session = load_session(
                season=season,
                event=round_number,
                session_id=session_type,
                cache_dir=self.cache_dir,
                laps=True,
                telemetry=False,
                weather=True,
                messages=True,
            )
        except Exception as exc:
            err_msg = f"Failed to acquire session data: {exc}"
            logger.error(err_msg)
            self.db.log_ingestion(
                status="FAILED",
                message=err_msg,
                season=season,
                round_number=round_number,
                session_type=session_type,
                duration_seconds=round(time.time() - start_time, 2),
            )
            update_progress(err_msg, 1.0)
            return IngestionResult(
                season=season,
                round_number=round_number,
                session_type=session_type,
                status="FAILED",
                records_ingested=0,
                duration_seconds=round(time.time() - start_time, 2),
                message=err_msg,
            )

        # 3. Ensure Event Record Exists in DB
        event_name = "Grand Prix"
        if hasattr(session, "event") and session.event is not None:
            event_name = str(session.event.get("EventName", event_name))
        event_dict = {
            "season": season,
            "round_number": round_number,
            "event_name": event_name,
            "event_date": str(session.date) if hasattr(session, "date") else "",
        }
        event_id = self.db.upsert_event(event_dict)

        # Ensure Session master record exists before child result insertions
        self.db.upsert_session(
            {
                "id": session_id,
                "event_id": event_id,
                "season": season,
                "round_number": round_number,
                "session_type": session_type,
                "session_name": f"{event_name} {session_type}",
                "session_date": str(session.date) if hasattr(session, "date") else "",
            }
        )

        update_progress(f"Processing classification and laps for {session_id}...", 0.40)

        # 4. Extract & Validate Session Results
        total_records = 0
        all_warnings: list[dict[str, Any]] = []

        raw_results: list[dict[str, Any]] = []
        has_results = (
            hasattr(session, "results")
            and session.results is not None
            and not session.results.empty
        )
        if has_results:
            for _, r in session.results.iterrows():
                raw_code = str(r.get("Abbreviation", "")).strip().upper()
                if not raw_code:
                    continue
                d_id = map_driver(raw_code, season=season)
                raw_team = str(r.get("TeamName", "Unknown"))
                c_id = map_constructor(raw_team, season=season)

                # Parse timing values
                fastest_sec = DataValidator._to_seconds(r.get("FastestLapTime"))
                total_time_sec = DataValidator._to_seconds(r.get("Time"))

                q1_sec = DataValidator._to_seconds(r.get("Q1"))
                q2_sec = DataValidator._to_seconds(r.get("Q2"))
                q3_sec = DataValidator._to_seconds(r.get("Q3"))

                pos_val = r.get("Position")
                finish_pos = (
                    int(pos_val)
                    if (pd.notna(pos_val) and str(pos_val).isdigit() and int(pos_val) > 0)
                    else None
                )

                grid_val = r.get("GridPosition")
                grid_pos = (
                    int(grid_val)
                    if (pd.notna(grid_val) and str(grid_val).isdigit())
                    else None
                )

                pts_val = r.get("Points")
                points = float(pts_val) if pd.notna(pts_val) else 0.0

                raw_results.append(
                    {
                        "driver_number": str(r.get("DriverNumber", d_id.driver_number)),
                        "driver_code": d_id.driver_code,
                        "driver_name": str(r.get("FullName", d_id.full_name)),
                        "constructor_id": c_id.constructor_id,
                        "constructor_name": c_id.name,
                        "grid_position": grid_pos,
                        "finish_position": finish_pos,
                        "classified_position": str(r.get("ClassifiedPosition", "")),
                        "points": points,
                        "finish_status": str(r.get("Status", "Finished")),
                        "q1_time": q1_sec,
                        "q2_time": q2_sec,
                        "q3_time": q3_sec,
                        "fastest_lap_time": fastest_sec,
                        "fastest_lap_rank": (
                            int(r.get("FastestLapRank"))
                            if pd.notna(r.get("FastestLapRank"))
                            else None
                        ),
                        "total_time_seconds": total_time_sec,
                    }
                )

        clean_results, res_warnings = DataValidator.validate_results(raw_results, session_id)
        all_warnings.extend(res_warnings)
        if clean_results:
            saved_count = self.db.save_session_results(session_id, clean_results)
            total_records += saved_count

        update_progress(f"Cleaning and saving laps for {session_id}...", 0.65)

        # 5. Extract, Validate & Save Laps to Parquet
        has_laps = False
        parquet_laps_path = ""
        laps_checksum = ""
        total_laps_count = 0
        total_drivers_count = len(clean_results)

        if hasattr(session, "laps") and session.laps is not None and not session.laps.empty:
            clean_laps, lap_warnings = DataValidator.validate_laps(session.laps, session_id)
            all_warnings.extend(lap_warnings)
            if not clean_laps.empty:
                out_path = self.parquet_store.save_laps(
                    season, round_number, session_type, clean_laps
                )
                parquet_laps_path = str(out_path)
                has_laps = True
                total_laps_count = len(clean_laps)
                total_records += total_laps_count
                laps_checksum = DataSourceRegistry.compute_dataframe_checksum(clean_laps)

        update_progress(f"Saving weather and race control events for {session_id}...", 0.85)

        # 6. Extract & Save Weather to Parquet
        has_weather = False
        parquet_weather_path = ""
        if (
            hasattr(session, "weather_data")
            and session.weather_data is not None
            and not session.weather_data.empty
        ):
            w_path = self.parquet_store.save_weather(
                season, round_number, session_type, session.weather_data
            )
            parquet_weather_path = str(w_path)
            has_weather = True
            total_records += len(session.weather_data)

        # 7. Extract & Save Race Control Events to SQLite
        if (
            hasattr(session, "race_control_messages")
            and session.race_control_messages is not None
            and not session.race_control_messages.empty
        ):
            rc_events: list[dict[str, Any]] = []
            for _, row in session.race_control_messages.iterrows():
                rc_events.append(
                    {
                        "lap_number": (
                            int(row.get("Lap"))
                            if (pd.notna(row.get("Lap")) and str(row.get("Lap")).isdigit())
                            else None
                        ),
                        "timestamp": str(row.get("Time", "")),
                        "category": str(row.get("Category", "Flag")),
                        "status": str(row.get("Status", "")),
                        "message": str(row.get("Message", "")),
                    }
                )
            if rc_events:
                self.db.save_race_control_events(session_id, rc_events)

        # 8. Log Data Quality Warnings to SQLite
        for w in all_warnings:
            self.db.log_data_warning(
                check_name=w["check_name"],
                severity=w["severity"],
                message=w["message"],
                session_id=session_id,
                field_name=w.get("field_name"),
                raw_value=w.get("raw_value"),
            )

        # 9. Record Source Provenance
        DataSourceRegistry.record_provenance(
            db=self.db,
            dataset_key=f"session_{session_id}",
            source_id="fastf1",
            season=season,
            record_count=total_records,
            event_id=event_id,
            session_id=session_id,
            data_availability="COMPLETE" if (has_laps and clean_results) else "PARTIAL",
            checksum=laps_checksum,
        )

        # 10. Update Session Master Record
        self.db.upsert_session(
            {
                "id": session_id,
                "event_id": event_id,
                "season": season,
                "round_number": round_number,
                "session_type": session_type,
                "session_name": f"{event_name} {session_type}",
                "session_date": str(session.date) if hasattr(session, "date") else "",
                "total_laps": total_laps_count,
                "total_drivers": total_drivers_count,
                "has_laps": has_laps,
                "has_weather": has_weather,
                "has_telemetry": False,
                "parquet_laps_path": parquet_laps_path,
                "parquet_weather_path": parquet_weather_path,
            }
        )

        # 11. Finalize Metadata and Log
        duration = round(time.time() - start_time, 2)
        status = "WARNING" if all_warnings else "SUCCESS"
        succ_msg = (
            f"Successfully ingested {session_id} ({total_laps_count} laps, "
            f"{len(clean_results)} drivers, {len(all_warnings)} warnings) in {duration}s."
        )
        self.db.log_ingestion(
            status=status,
            message=succ_msg,
            season=season,
            round_number=round_number,
            session_type=session_type,
            records_ingested=total_records,
            duration_seconds=duration,
        )
        self.db.set_metadata(
            "last_successful_sync",
            datetime.datetime.now(datetime.UTC).isoformat(),
        )

        update_progress(succ_msg, 1.0)
        logger.info(succ_msg)

        return IngestionResult(
            season=season,
            round_number=round_number,
            session_type=session_type,
            status=status,
            records_ingested=total_records,
            duration_seconds=duration,
            message=succ_msg,
            warnings_count=len(all_warnings),
        )
