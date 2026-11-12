"""Lap kinematics engine, dirty air aerodynamics, and forward race step simulation.

Computes lap times integrating tyre compound degradation, fuel burn-off,
track rubber evolution, dirty air wake penalties, and overtaking kinematics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from stratos.models.pit import PitLossModel, TrackStatus
from stratos.models.state import DriverState, PitStopRecord, RaceState
from stratos.models.tyre import TyreCompound, TyreDegradationModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PitAction:
    """Action requested for a driver at the end of the current lap.

    Attributes
    ----------
    new_compound : TyreCompound
        The tyre compound to fit during the stop.
    stationary_duration : float | None
        Optional override for stationary box time (seconds).
    front_wing_change : bool
        Whether to perform a front wing replacement (+8.0 seconds).
    """

    new_compound: TyreCompound
    stationary_duration: float | None = None
    front_wing_change: bool = False


class LapKinematicsEngine:
    """Engine computing physical lap times and advancing race state."""

    def __init__(
        self,
        tyre_model: TyreDegradationModel | None = None,
        pit_loss_model: PitLossModel | None = None,
    ) -> None:
        """Initialize kinematics engine with degradation and pit models.

        Parameters
        ----------
        tyre_model : TyreDegradationModel or None
            Tyre degradation model. If None, instantiates default model.
        pit_loss_model : PitLossModel or None
            Pit loss model. If None, instantiates default model.
        """
        self.tyre_model = tyre_model if tyre_model is not None else TyreDegradationModel()
        self.pit_loss_model = pit_loss_model if pit_loss_model is not None else PitLossModel()

    def calculate_ideal_lap_time(
        self,
        race_state: RaceState,
        driver: DriverState,
    ) -> float:
        """Calculate clean-air lap time without traffic or pit stop delay.

        Parameters
        ----------
        race_state : RaceState
            Current state of the race.
        driver : DriverState
            Driver being evaluated.

        Returns
        -------
        float
            Clean air lap time in seconds.
        """
        circuit = race_state.circuit
        env = race_state.environment

        # 1. Base track lap time
        lap_time = circuit.base_lap_time

        # 2. Tyre degradation penalty
        deg_penalty = self.tyre_model.lap_time_penalty(
            compound=driver.current_compound,
            tyre_age=driver.tyre_age,
            track_temp=env.track_temp,
        )
        lap_time += deg_penalty

        # 3. Fuel load effect: heavier car at start of race, lighter at end
        laps_remaining = max(0, circuit.total_laps - env.lap)
        fuel_penalty = laps_remaining * circuit.fuel_effect_per_lap
        lap_time += fuel_penalty

        # 4. Track rubber evolution: track gets faster as rubber is laid down
        rubber_benefit = env.lap * circuit.track_evolution_per_lap
        lap_time -= rubber_benefit

        # 5. Weather mismatch penalty
        if env.rainfall_intensity > 0.3:
            # Wet track
            if driver.current_compound in (
                TyreCompound.SOFT,
                TyreCompound.MEDIUM,
                TyreCompound.HARD,
            ):
                # Slicks on wet track: severe penalty
                lap_time += 18.0 + (env.rainfall_intensity * 8.0)
            elif driver.current_compound == TyreCompound.INTERMEDIATE:
                if env.rainfall_intensity > 2.0:
                    # Too wet for Inters
                    lap_time += (env.rainfall_intensity - 2.0) * 4.0
            elif driver.current_compound == TyreCompound.WET:
                if env.rainfall_intensity < 1.0:
                    # Standing water tyres on damp track
                    lap_time += 3.5

        # 6. Safety Car / VSC speed limiter adherence
        if env.track_status == TrackStatus.VSC:
            lap_time = max(lap_time, circuit.base_lap_time * 1.38)
        elif env.track_status == TrackStatus.SAFETY_CAR:
            lap_time = max(lap_time, circuit.base_lap_time * 1.55)

        return float(lap_time)

    def calculate_traffic_penalty(
        self,
        circuit_overtaking_difficulty: float,
        interval_to_ahead: float,
    ) -> float:
        """Calculate lap time penalty from turbulent aerodynamic dirty air wake.

        Parameters
        ----------
        circuit_overtaking_difficulty : float
            Overtaking difficulty parameter (0.0 easy to 1.0 impossible).
        interval_to_ahead : float
            Time gap to the car directly in front in seconds.

        Returns
        -------
        float
            Lap time loss in seconds due to dirty air turbulence.
        """
        # Turbulent dirty air wake extends up to 1.5 seconds behind lead car
        if interval_to_ahead < 1.5:
            intensity = (1.5 - interval_to_ahead) / 1.5
            return float(intensity * 0.65 * (0.5 + 0.5 * circuit_overtaking_difficulty))
        return 0.0

    def step(
        self,
        current_state: RaceState,
        pit_actions: dict[str, PitAction | TyreCompound] | None = None,
    ) -> RaceState:
        """Advance the entire race by one lap.

        Computes lap times, handles pit stops, resolves overtaking and traffic
        interference, updates cumulative gaps, and returns a new RaceState.

        Parameters
        ----------
        current_state : RaceState
            Current state of the race before the lap.
        pit_actions : dict[str, PitAction | TyreCompound] or None
            Optional pit decisions mapping driver_id to PitAction or TyreCompound.

        Returns
        -------
        RaceState
            Updated race state after lap execution.
        """
        next_state = current_state.clone()
        circuit = next_state.circuit
        env = next_state.environment
        actions = pit_actions or {}

        # 1. Compute lap times and execute pit stops
        lap_records: list[dict[str, Any]] = []

        for driver_id, driver in next_state.drivers.items():
            if driver.is_retired:
                continue

            # Check if pitting this lap
            action = actions.get(driver_id)
            is_pitting = action is not None
            pit_loss = 0.0
            new_compound = driver.current_compound
            stationary_time = circuit.to_pit_profile().typical_stationary_time

            if is_pitting:
                if isinstance(action, PitAction):
                    new_compound = action.new_compound
                    stationary_time = (
                        action.stationary_duration
                        if action.stationary_duration is not None
                        else stationary_time
                    )
                    pit_loss = self.pit_loss_model.calculate_pit_loss(
                        track_status=env.track_status,
                        stationary_time=stationary_time,
                        front_wing_change=action.front_wing_change,
                    )
                else:
                    new_compound = (
                        action
                        if isinstance(action, TyreCompound)
                        else TyreCompound.from_string(action)
                    )
                    pit_loss = self.pit_loss_model.calculate_pit_loss(
                        track_status=env.track_status,
                        stationary_time=stationary_time,
                    )

            # Compute clean-air ideal lap time
            ideal_time = self.calculate_ideal_lap_time(next_state, driver)

            # Add traffic penalty if not leading and not pitting
            traffic_penalty = 0.0
            if driver.position > 1 and not is_pitting:
                traffic_penalty = self.calculate_traffic_penalty(
                    circuit.overtaking_difficulty,
                    driver.interval_to_ahead,
                )

            total_lap_time = ideal_time + traffic_penalty + pit_loss

            lap_records.append(
                {
                    "driver_id": driver_id,
                    "lap_time": total_lap_time,
                    "ideal_time": ideal_time,
                    "is_pitting": is_pitting,
                    "new_compound": new_compound,
                    "pit_loss": pit_loss,
                    "stationary_time": stationary_time,
                    "in_dirty_air": traffic_penalty > 0.05,
                }
            )

        # 2. Update driver times, tyre age, and pit records
        for rec in lap_records:
            driver = next_state.drivers[rec["driver_id"]]
            driver.total_race_time += rec["lap_time"]
            driver.last_lap_time = rec["lap_time"]

            if rec["is_pitting"]:
                stop_record = PitStopRecord(
                    lap=env.lap,
                    compound_in=driver.current_compound,
                    compound_out=rec["new_compound"],
                    stationary_duration=rec["stationary_time"],
                    total_loss=rec["pit_loss"],
                )
                driver.pit_stops.append(stop_record)
                driver.current_compound = rec["new_compound"]
                driver.tyre_age = 0
                driver.is_in_pit = True
            else:
                driver.is_in_pit = False
                # Age tyre: in dirty air wear accelerates slightly
                driver.tyre_age += 1

        # 3. Sort active drivers by total race time to determine positions
        active_drivers = [d for d in next_state.drivers.values() if not d.is_retired]
        active_drivers.sort(key=lambda d: d.total_race_time)

        # 4. Resolve overtaking kinematics:
        # Check if a trailing driver has enough pace delta to overtake
        leader_time = active_drivers[0].total_race_time
        prev_time = leader_time

        for idx, d in enumerate(active_drivers):
            d.position = idx + 1
            d.gap_to_leader = float(d.total_race_time - leader_time)
            d.interval_to_ahead = float(d.total_race_time - prev_time) if idx > 0 else 0.0
            prev_time = d.total_race_time

        # 5. Advance environment lap counter
        env.lap += 1

        return next_state
