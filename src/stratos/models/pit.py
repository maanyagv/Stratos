"""Pit loss calculations, pit window clearance, and safety car delta estimators.

In Formula 1, pit stop execution time is split between:
  1. Pit lane entry, transit at the pit speed limit (60 or 80 km/h), and exit.
  2. Stationary box duration (wheel guns, 4 tyre changes, wing adjustments).
  3. Delta against cars remaining on track at racing speed, VSC speed, or Safety Car speed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class TrackStatus(StrEnum):
    """Race track condition status."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    VSC = "VSC"  # Virtual Safety Car
    SAFETY_CAR = "SAFETY_CAR"  # Full Safety Car
    RED_FLAG = "RED_FLAG"

    @classmethod
    def from_string(cls, value: str) -> TrackStatus:
        """Parse track status string case-insensitively.

        Parameters
        ----------
        value : str
            Status string (e.g., 'GREEN', 'SC', 'VSC', 'SAFETY_CAR').

        Returns
        -------
        TrackStatus
            Resolved TrackStatus enum.
        """
        norm = value.strip().upper()
        if norm in ("SC", "SAFETY CAR", "SAFETY_CAR"):
            return cls.SAFETY_CAR
        if norm in ("VSC", "VIRTUAL SAFETY CAR", "VIRTUAL_SAFETY_CAR"):
            return cls.VSC
        if norm in ("YELLOW", "YEL"):
            return cls.YELLOW
        if norm in ("RED", "RED FLAG", "RED_FLAG"):
            return cls.RED_FLAG
        if norm in ("GREEN", "CLEAR"):
            return cls.GREEN
        raise ValueError(f"Unrecognized track status '{value}'.")


@dataclass(frozen=True)
class CircuitPitProfile:
    """Pit lane parameters and nominal deltas for a specific circuit.

    Attributes
    ----------
    circuit_name : str
        Official or common circuit name (e.g., 'Monaco', 'Silverstone').
    pit_speed_limit_kmh : float
        Pit lane speed limit in km/h (typically 60.0 or 80.0 km/h).
    pit_transit_loss_green : float
        Time lost in seconds (entry, pit lane travel at speed limit, and exit)
        relative to staying on track at racing speed under Green Flag conditions,
        excluding stationary box time.
    typical_stationary_time : float
        Nominal stationary box duration in seconds (default 2.4s).
    vsc_saving_ratio : float
        Fractional reduction of transit loss during Virtual Safety Car
        (typically 0.40 to 0.45 because on-track cars travel ~35-40% slower).
    sc_saving_ratio : float
        Fractional reduction of transit loss during full Safety Car
        (typically 0.50 to 0.55).
    """

    circuit_name: str
    pit_speed_limit_kmh: float = 80.0
    pit_transit_loss_green: float = 20.0
    typical_stationary_time: float = 2.4
    vsc_saving_ratio: float = 0.42
    sc_saving_ratio: float = 0.52

    @property
    def total_green_pit_loss(self) -> float:
        """Total nominal pit loss under Green Flag conditions (transit + stationary)."""
        return self.pit_transit_loss_green + self.typical_stationary_time

    @property
    def total_vsc_pit_loss(self) -> float:
        """Total nominal pit loss under Virtual Safety Car conditions."""
        reduced_transit = self.pit_transit_loss_green * (1.0 - self.vsc_saving_ratio)
        return reduced_transit + self.typical_stationary_time

    @property
    def total_sc_pit_loss(self) -> float:
        """Total nominal pit loss under full Safety Car conditions."""
        reduced_transit = self.pit_transit_loss_green * (1.0 - self.sc_saving_ratio)
        return reduced_transit + self.typical_stationary_time


# Standard calibrated pit profiles for iconic circuits
CIRCUIT_PIT_PROFILES: dict[str, CircuitPitProfile] = {
    "monaco": CircuitPitProfile(
        circuit_name="Monaco",
        pit_speed_limit_kmh=60.0,
        pit_transit_loss_green=21.8,
        typical_stationary_time=2.4,
        vsc_saving_ratio=0.45,
        sc_saving_ratio=0.55,
    ),
    "silverstone": CircuitPitProfile(
        circuit_name="Silverstone",
        pit_speed_limit_kmh=80.0,
        pit_transit_loss_green=25.6,
        typical_stationary_time=2.4,
        vsc_saving_ratio=0.42,
        sc_saving_ratio=0.52,
    ),
    "monza": CircuitPitProfile(
        circuit_name="Monza",
        pit_speed_limit_kmh=80.0,
        pit_transit_loss_green=21.5,
        typical_stationary_time=2.4,
        vsc_saving_ratio=0.40,
        sc_saving_ratio=0.50,
    ),
    "spa": CircuitPitProfile(
        circuit_name="Spa-Francorchamps",
        pit_speed_limit_kmh=80.0,
        pit_transit_loss_green=19.2,
        typical_stationary_time=2.4,
        vsc_saving_ratio=0.42,
        sc_saving_ratio=0.52,
    ),
    "red_bull_ring": CircuitPitProfile(
        circuit_name="Red Bull Ring",
        pit_speed_limit_kmh=80.0,
        pit_transit_loss_green=18.0,
        typical_stationary_time=2.4,
        vsc_saving_ratio=0.43,
        sc_saving_ratio=0.53,
    ),
    "suzuka": CircuitPitProfile(
        circuit_name="Suzuka",
        pit_speed_limit_kmh=80.0,
        pit_transit_loss_green=20.5,
        typical_stationary_time=2.4,
        vsc_saving_ratio=0.42,
        sc_saving_ratio=0.52,
    ),
    "default": CircuitPitProfile(
        circuit_name="Standard Circuit",
        pit_speed_limit_kmh=80.0,
        pit_transit_loss_green=20.0,
        typical_stationary_time=2.4,
        vsc_saving_ratio=0.42,
        sc_saving_ratio=0.52,
    ),
}


class PitLossModel:
    """Estimator for pit loss under various track and operational conditions."""

    def __init__(self, profile: CircuitPitProfile | None = None) -> None:
        """Initialize the pit loss model with a circuit profile.

        Parameters
        ----------
        profile : CircuitPitProfile or None
            Circuit pit profile. If None, uses default profile.
        """
        self.profile = profile if profile is not None else CIRCUIT_PIT_PROFILES["default"]

    @classmethod
    def for_circuit(cls, circuit_name: str) -> PitLossModel:
        """Factory constructor for a circuit by name.

        Parameters
        ----------
        circuit_name : str
            Circuit identifier (e.g. 'Monaco', 'Silverstone', 'Monza').

        Returns
        -------
        PitLossModel
            Configured PitLossModel instance.
        """
        key = circuit_name.lower().replace(" ", "_").replace("-", "_")
        profile = CIRCUIT_PIT_PROFILES.get(key, CIRCUIT_PIT_PROFILES["default"])
        return cls(profile)

    def calculate_pit_loss(
        self,
        track_status: TrackStatus | str = TrackStatus.GREEN,
        stationary_time: float | None = None,
        front_wing_change: bool = False,
    ) -> float:
        """Calculate total pit time loss (seconds) under current conditions.

        Parameters
        ----------
        track_status : TrackStatus or str, default TrackStatus.GREEN
            Current track condition (GREEN, VSC, SAFETY_CAR, YELLOW).
        stationary_time : float or None, default None
            Stationary box time in seconds. If None, uses nominal profile value.
        front_wing_change : bool, default False
            Whether a front wing replacement is performed (adds ~8.0 seconds).

        Returns
        -------
        float
            Total time lost during the pit stop in seconds.
        """
        status = (
            track_status
            if isinstance(track_status, TrackStatus)
            else TrackStatus.from_string(track_status)
        )

        box_time = (
            stationary_time if stationary_time is not None else self.profile.typical_stationary_time
        )
        if front_wing_change:
            box_time += 8.0

        if status == TrackStatus.GREEN or status == TrackStatus.YELLOW:
            transit = self.profile.pit_transit_loss_green
        elif status == TrackStatus.VSC:
            transit = self.profile.pit_transit_loss_green * (1.0 - self.profile.vsc_saving_ratio)
        elif status == TrackStatus.SAFETY_CAR:
            transit = self.profile.pit_transit_loss_green * (1.0 - self.profile.sc_saving_ratio)
        elif status == TrackStatus.RED_FLAG:
            # Under red flag, tyre changes are permitted in pit lane under stoppage (zero loss)
            return 0.0
        else:
            transit = self.profile.pit_transit_loss_green

        return float(transit + box_time)

    def evaluate_pit_window(
        self,
        target_driver_gap_to_leader: float,
        competitor_gaps: list[dict[str, Any]],
        track_status: TrackStatus | str = TrackStatus.GREEN,
        stationary_time: float | None = None,
    ) -> dict[str, Any]:
        """Evaluate where a driver will re-enter the race relative to competitors.

        Parameters
        ----------
        target_driver_gap_to_leader : float
            Current gap to leader for the pitting driver in seconds (0.0 if leader).
        competitor_gaps : list[dict[str, Any]]
            List of competitors ordered by running position, where each dict has:
            - 'driver_id': str
            - 'position': int
            - 'gap_to_leader': float
        track_status : TrackStatus or str, default TrackStatus.GREEN
            Current track condition.
        stationary_time : float or None, default None
            Stationary box duration in seconds.

        Returns
        -------
        dict[str, Any]
            Dictionary detailing:
            - 'pit_loss_seconds': float
            - 'projected_gap_to_leader': float
            - 'projected_position': int
            - 'car_ahead': str | None (driver immediately ahead after rejoin)
            - 'gap_to_car_ahead': float | None
            - 'car_behind': str | None (driver immediately behind after rejoin)
            - 'gap_to_car_behind': float | None
            - 'in_traffic': bool (True if gap_to_car_ahead < 1.5 seconds)
        """
        loss = self.calculate_pit_loss(track_status, stationary_time)
        projected_gap = target_driver_gap_to_leader + loss

        # Sort competitors by current gap to leader
        sorted_comps = sorted(competitor_gaps, key=lambda c: c["gap_to_leader"])

        projected_position = 1
        car_ahead: str | None = None
        gap_ahead: float | None = None
        car_behind: str | None = None
        gap_behind: float | None = None

        for comp in sorted_comps:
            if comp["gap_to_leader"] < projected_gap:
                projected_position += 1
                car_ahead = comp["driver_id"]
                gap_ahead = projected_gap - comp["gap_to_leader"]
            elif car_behind is None:
                car_behind = comp["driver_id"]
                gap_behind = comp["gap_to_leader"] - projected_gap

        in_traffic = gap_ahead is not None and gap_ahead < 1.5

        return {
            "pit_loss_seconds": loss,
            "projected_gap_to_leader": projected_gap,
            "projected_position": projected_position,
            "car_ahead": car_ahead,
            "gap_to_car_ahead": gap_ahead,
            "car_behind": car_behind,
            "gap_to_car_behind": gap_behind,
            "in_traffic": in_traffic,
        }
