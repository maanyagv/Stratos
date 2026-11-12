"""Race state representation and multi-car grid modeling.

Provides strongly-typed, immutable dataclasses for driver kinematics,
compound history, FIA regulatory compliance (e.g. 2-compound rule),
environmental conditions, and circuit parameters.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from stratos.models.pit import CircuitPitProfile, PitLossModel, TrackStatus
from stratos.models.tyre import TyreCompound

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PitStopRecord:
    """Historical record of an individual pit stop.

    Attributes
    ----------
    lap : int
        Race lap on which the pit stop occurred.
    compound_in : TyreCompound
        Tyre compound taken off the car.
    compound_out : TyreCompound
        New tyre compound fitted to the car.
    stationary_duration : float
        Time spent stationary in the pit box (seconds).
    total_loss : float
        Total time loss relative to staying on track (seconds).
    """

    lap: int
    compound_in: TyreCompound
    compound_out: TyreCompound
    stationary_duration: float
    total_loss: float


@dataclass
class DriverState:
    """Dynamic kinematic state and strategy status of an individual competitor.

    Attributes
    ----------
    driver_id : str
        Driver code / abbreviation (e.g., 'VER', 'HAM', 'NOR').
    team : str
        Constructor name (e.g., 'Red Bull Racing', 'Ferrari').
    position : int
        Current running position (1-indexed).
    gap_to_leader : float
        Cumulative gap to the race leader in seconds (0.0 for leader).
    interval_to_ahead : float
        Time delta to the competitor directly ahead in seconds (0.0 for leader).
    current_compound : TyreCompound
        Currently fitted tyre compound.
    tyre_age : int
        Completed laps on the current set of tyres.
    pit_stops : list[PitStopRecord]
        List of completed pit stops.
    total_race_time : float
        Cumulative elapsed race time in seconds.
    last_lap_time : float | None
        Duration of the most recently completed lap in seconds.
    is_in_pit : bool
        Whether the car is currently in the pit lane.
    is_retired : bool
        Whether the car has retired from the race.
    """

    driver_id: str
    team: str
    position: int
    gap_to_leader: float
    interval_to_ahead: float
    current_compound: TyreCompound
    tyre_age: int = 0
    pit_stops: list[PitStopRecord] = field(default_factory=list)
    total_race_time: float = 0.0
    last_lap_time: float | None = None
    is_in_pit: bool = False
    is_retired: bool = False

    @property
    def stint_number(self) -> int:
        """Current stint number (1-indexed)."""
        return len(self.pit_stops) + 1

    @property
    def compounds_used(self) -> set[TyreCompound]:
        """Set of all tyre compounds used by the driver so far."""
        used = {self.current_compound}
        for stop in self.pit_stops:
            used.add(stop.compound_in)
            used.add(stop.compound_out)
        return used

    def satisfies_two_compound_rule(self) -> bool:
        """Check whether the driver has complied with the FIA dry tyre regulation.

        In dry races, drivers must use at least two distinct dry tyre compounds
        (Soft, Medium, Hard). If Intermediate or Wet tyres have been fitted,
        this requirement is waived under FIA regulations.

        Returns
        -------
        bool
            True if the tyre regulation is satisfied, False otherwise.
        """
        used = self.compounds_used
        # If wet/intermediate tyres used, regulation is satisfied
        if TyreCompound.INTERMEDIATE in used or TyreCompound.WET in used:
            return True

        dry_compounds_used = used.intersection(
            {TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD}
        )
        return len(dry_compounds_used) >= 2


@dataclass(frozen=True)
class CircuitConfig:
    """Circuit characteristics and kinematic parameters.

    Attributes
    ----------
    name : str
        Circuit name (e.g., 'Monaco', 'Silverstone').
    total_laps : int
        Scheduled race distance in laps.
    base_lap_time : float
        Reference lap time (seconds) on fresh Softs with zero fuel at race start.
    pit_transit_loss_green : float
        Pit entry/transit/exit time loss under Green Flag in seconds.
    fuel_effect_per_lap : float
        Lap time reduction (seconds/lap) as fuel burns down (default 0.033s).
    track_evolution_per_lap : float
        Lap time reduction (seconds/lap) from rubbering in (default 0.015s).
    overtaking_difficulty : float
        Difficulty score from 0.0 (very easy, e.g. Monza) to 1.0 (almost impossible, e.g. Monaco).
    """

    name: str
    total_laps: int
    base_lap_time: float
    pit_transit_loss_green: float = 20.0
    fuel_effect_per_lap: float = 0.033
    track_evolution_per_lap: float = 0.015
    overtaking_difficulty: float = 0.50

    def to_pit_profile(self) -> CircuitPitProfile:
        """Convert circuit config to CircuitPitProfile."""
        return CircuitPitProfile(
            circuit_name=self.name,
            pit_transit_loss_green=self.pit_transit_loss_green,
        )


@dataclass
class EnvironmentState:
    """Environmental and race control condition state.

    Attributes
    ----------
    lap : int
        Current race lap (1-indexed).
    total_laps : int
        Total scheduled race distance.
    track_status : TrackStatus
        Current race control track status (GREEN, VSC, SAFETY_CAR, YELLOW).
    track_temp : float
        Track surface temperature in °C.
    air_temp : float
        Ambient air temperature in °C.
    rainfall_intensity : float
        Precipitation intensity in mm/hour (0.0 = completely dry).
    """

    lap: int
    total_laps: int
    track_status: TrackStatus = TrackStatus.GREEN
    track_temp: float = 35.0
    air_temp: float = 25.0
    rainfall_intensity: float = 0.0

    @property
    def is_wet(self) -> bool:
        """Whether track conditions require wet or intermediate tyres."""
        return self.rainfall_intensity > 0.2


@dataclass
class RaceState:
    """Comprehensive state of the race, circuit, environment, and competitor grid.

    Attributes
    ----------
    circuit : CircuitConfig
        Circuit configuration and physical properties.
    environment : EnvironmentState
        Track and environmental conditions.
    drivers : dict[str, DriverState]
        Mapping of driver IDs to their current DriverState.
    """

    circuit: CircuitConfig
    environment: EnvironmentState
    drivers: dict[str, DriverState]

    def get_driver(self, driver_id: str) -> DriverState:
        """Get state for a specific driver.

        Parameters
        ----------
        driver_id : str
            Driver ID code.

        Returns
        -------
        DriverState
            State of the requested driver.

        Raises
        ------
        KeyError
            If the driver ID is not in the race grid.
        """
        if driver_id not in self.drivers:
            raise KeyError(f"Driver '{driver_id}' not found in active race state.")
        return self.drivers[driver_id]

    def get_leader(self) -> DriverState:
        """Get the current race leader (position 1).

        Returns
        -------
        DriverState
            Current leader.

        Raises
        ------
        ValueError
            If no active drivers exist.
        """
        for d in self.drivers.values():
            if d.position == 1 and not d.is_retired:
                return d
        # Fallback to minimum gap
        active = [d for d in self.drivers.values() if not d.is_retired]
        if not active:
            raise ValueError("No active drivers in race state.")
        return min(active, key=lambda d: d.gap_to_leader)

    def get_standings(self) -> list[DriverState]:
        """Return all drivers ordered by running position.

        Returns
        -------
        list[DriverState]
            Drivers sorted from position 1 to N.
        """
        return sorted(self.drivers.values(), key=lambda d: (d.is_retired, d.position))

    def predict_pit_rejoin(
        self,
        driver_id: str,
        pit_loss_model: PitLossModel | None = None,
        stationary_time: float | None = None,
    ) -> dict[str, Any]:
        """Predict the track position and traffic conditions if driver pits now.

        Parameters
        ----------
        driver_id : str
            Target driver ID.
        pit_loss_model : PitLossModel or None
            Pit loss estimator. If None, instantiates one from circuit config.
        stationary_time : float or None
            Stationary box time in seconds.

        Returns
        -------
        dict[str, Any]
            Traffic projection and gap assessment.
        """
        driver = self.get_driver(driver_id)
        model = (
            pit_loss_model
            if pit_loss_model is not None
            else PitLossModel(self.circuit.to_pit_profile())
        )

        competitors = [
            {
                "driver_id": d.driver_id,
                "position": d.position,
                "gap_to_leader": d.gap_to_leader,
            }
            for d in self.drivers.values()
            if d.driver_id != driver_id and not d.is_retired
        ]

        return model.evaluate_pit_window(
            target_driver_gap_to_leader=driver.gap_to_leader,
            competitor_gaps=competitors,
            track_status=self.environment.track_status,
            stationary_time=stationary_time,
        )

    def clone(self) -> RaceState:
        """Deep copy the race state for branching simulation or lookahead search.

        Returns
        -------
        RaceState
            Independent deep copy of the state.
        """
        return copy.deepcopy(self)
