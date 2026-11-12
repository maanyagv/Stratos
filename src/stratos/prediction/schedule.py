"""Automatic Next Grand Prix calendar schedule detection for STRATOS.

Determines the next scheduled Formula 1 Grand Prix using official FastF1 schedule
data or database records dynamically without hardcoded names or dates.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import fastf1
import pandas as pd

if TYPE_CHECKING:
    from stratos.storage.database import StratosDB

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NextEventInfo:
    """Information for the next scheduled Grand Prix event."""

    season: int
    round_number: int
    event_name: str
    official_name: str
    country: str
    location: str
    event_date: str
    is_sprint: bool
    status: str  # 'SCHEDULED', 'SEASON_COMPLETE', 'SCHEDULE_UNAVAILABLE'
    days_until_event: int | None
    circuit_key: str = ""


class NextEventDetector:
    """Detects upcoming Grand Prix events from official schedules."""

    def __init__(self, db: StratosDB | None = None) -> None:
        """Initialize the event detector.

        Parameters
        ----------
        db : StratosDB or None
            Database manager for fallback schedule queries.
        """
        self.db = db

    def get_next_event(
        self,
        reference_date: datetime.date | None = None,
        target_season: int | None = None,
    ) -> NextEventInfo:
        """Detect the next upcoming Formula 1 Grand Prix.

        Parameters
        ----------
        reference_date : datetime.date or None
            Date to measure against. Defaults to current UTC date.
        target_season : int or None
            Season year. Defaults to current year.

        Returns
        -------
        NextEventInfo
            Structured metadata for the next scheduled Grand Prix.
        """
        if reference_date is not None:
            now_date = reference_date
        else:
            now_date = datetime.datetime.now(datetime.UTC).date()
        current_year = target_season if target_season is not None else now_date.year

        # 1. Try retrieving official calendar from FastF1
        events_list = self._fetch_calendar_events(current_year)

        # 2. If no events found or all past, try target_season + 1 if near year-end
        if not events_list and target_season is None:
            events_list = self._fetch_calendar_events(current_year + 1)
            if events_list:
                current_year = current_year + 1

        if not events_list:
            # Fallback to database events if available
            if self.db:
                events_list = self._fetch_db_events(current_year)

        if not events_list:
            return NextEventInfo(
                season=current_year,
                round_number=1,
                event_name="Upcoming Grand Prix",
                official_name="Formula 1 World Championship Event",
                country="TBD",
                location="TBD",
                event_date=now_date.isoformat(),
                is_sprint=False,
                status="SCHEDULE_UNAVAILABLE",
                days_until_event=None,
            )

        # 3. Find the first event with event_date >= reference_date
        for ev in events_list:
            ev_date_str = ev.get("event_date", "")
            try:
                ev_date = datetime.date.fromisoformat(str(ev_date_str).split("T")[0])
            except (ValueError, TypeError):
                continue

            if ev_date >= now_date:
                days_diff = (ev_date - now_date).days
                return NextEventInfo(
                    season=ev["season"],
                    round_number=ev["round_number"],
                    event_name=ev["event_name"],
                    official_name=ev.get("official_name", ev["event_name"]),
                    country=ev.get("country", ""),
                    location=ev.get("location", ""),
                    event_date=ev_date.isoformat(),
                    is_sprint=ev.get("is_sprint", False),
                    status="SCHEDULED",
                    days_until_event=days_diff,
                    circuit_key=ev.get("circuit_key", ""),
                )

        # If all events in the season are in the past:
        last_ev = events_list[-1]
        return NextEventInfo(
            season=current_year,
            round_number=last_ev["round_number"],
            event_name=last_ev["event_name"],
            official_name=last_ev.get("official_name", last_ev["event_name"]),
            country=last_ev.get("country", ""),
            location=last_ev.get("location", ""),
            event_date=str(last_ev.get("event_date", "")),
            is_sprint=last_ev.get("is_sprint", False),
            status="SEASON_COMPLETE",
            days_until_event=None,
        )

    def _fetch_calendar_events(self, season: int) -> list[dict[str, Any]]:
        """Fetch and structure official calendar schedule from FastF1."""
        try:
            schedule = fastf1.get_event_schedule(season)
        except Exception as exc:
            logger.debug("FastF1 schedule retrieval unavailable for season %d: %s", season, exc)
            return []

        if schedule.empty:
            return []

        events: list[dict[str, Any]] = []
        for _, row in schedule.iterrows():
            rnd = row.get("RoundNumber")
            if pd.isna(rnd) or int(rnd) < 1:
                continue

            date_val = row.get("EventDate")
            date_str = str(date_val).split(" ")[0] if pd.notna(date_val) else ""

            format_val = str(row.get("EventFormat", "conventional"))
            is_sprint = "sprint" in format_val.lower()

            events.append(
                {
                    "season": season,
                    "round_number": int(rnd),
                    "event_name": str(row.get("EventName", f"Round {rnd}")),
                    "official_name": str(row.get("OfficialEventName", "")),
                    "country": str(row.get("Country", "")),
                    "location": str(row.get("Location", "")),
                    "event_date": date_str,
                    "is_sprint": is_sprint,
                }
            )

        return sorted(events, key=lambda x: x["round_number"])

    def _fetch_db_events(self, season: int) -> list[dict[str, Any]]:
        """Fetch stored events from database."""
        if not self.db:
            return []
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE season = ?
                ORDER BY round_number ASC;
                """,
                (season,),
            ).fetchall()
            return [dict(r) for r in rows]
