"""Unit tests for NextEventDetector dynamic schedule discovery."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pandas as pd

from stratos.prediction.schedule import NextEventDetector


def test_next_event_scheduled() -> None:
    """Verify that detector picks the earliest event on or after reference date."""
    mock_schedule = pd.DataFrame(
        {
            "RoundNumber": [1, 2, 3],
            "EventName": [
                "Bahrain Grand Prix",
                "Saudi Arabian Grand Prix",
                "Australian Grand Prix",
            ],
            "OfficialEventName": ["Formula 1 Bahrain GP", "Formula 1 Saudi GP", "Formula 1 Aus GP"],
            "Country": ["Bahrain", "Saudi Arabia", "Australia"],
            "Location": ["Sakhir", "Jeddah", "Melbourne"],
            "EventDate": [
                pd.Timestamp("2024-03-02"),
                pd.Timestamp("2024-03-09"),
                pd.Timestamp("2024-03-24"),
            ],
            "EventFormat": ["conventional", "conventional", "conventional"],
        }
    )

    detector = NextEventDetector(db=None)

    with patch("fastf1.get_event_schedule", return_value=mock_schedule):
        # On Feb 25, 2024 -> Next race is Bahrain (Round 1)
        ref_feb = datetime.date(2024, 2, 25)
        ev1 = detector.get_next_event(reference_date=ref_feb, target_season=2024)
        assert ev1.status == "SCHEDULED"
        assert ev1.round_number == 1
        assert ev1.event_name == "Bahrain Grand Prix"
        assert ev1.days_until_event == 6

        # On March 5, 2024 -> Bahrain is past; next race is Saudi (Round 2)
        ref_march = datetime.date(2024, 3, 5)
        ev2 = detector.get_next_event(reference_date=ref_march, target_season=2024)
        assert ev2.status == "SCHEDULED"
        assert ev2.round_number == 2
        assert ev2.event_name == "Saudi Arabian Grand Prix"
        assert ev2.days_until_event == 4


def test_season_complete_fallback() -> None:
    """Verify explicit status when all scheduled races in season are completed."""
    mock_schedule = pd.DataFrame(
        {
            "RoundNumber": [1],
            "EventName": ["Abu Dhabi Grand Prix"],
            "OfficialEventName": ["Formula 1 Abu Dhabi GP"],
            "Country": ["UAE"],
            "Location": ["Yas Marina"],
            "EventDate": [pd.Timestamp("2024-11-20")],
            "EventFormat": ["conventional"],
        }
    )

    detector = NextEventDetector(db=None)

    with patch("fastf1.get_event_schedule", return_value=mock_schedule):
        ref_dec = datetime.date(2024, 12, 1)
        ev = detector.get_next_event(reference_date=ref_dec, target_season=2024)
        assert ev.status == "SEASON_COMPLETE"
        assert ev.event_name == "Abu Dhabi Grand Prix"
        assert ev.days_until_event is None


def test_schedule_unavailable_graceful() -> None:
    """Verify graceful fallback without synthetic invention when schedule is empty."""
    detector = NextEventDetector(db=None)
    with patch("fastf1.get_event_schedule", return_value=pd.DataFrame()):
        ev = detector.get_next_event(reference_date=datetime.date(2024, 1, 1), target_season=2024)
        assert ev.status == "SCHEDULE_UNAVAILABLE"
        assert ev.days_until_event is None
