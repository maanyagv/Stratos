"""Unit tests for lap kinematics, dirty air penalties, and simulation forward stepping."""

from __future__ import annotations

import pytest

from stratos.models.kinematics import LapKinematicsEngine, PitAction
from stratos.models.pit import TrackStatus
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    RaceState,
)
from stratos.models.tyre import TyreCompound


def test_calculate_ideal_lap_time() -> None:
    """Verify clean air lap time composition (fuel burn, rubbering in, deg)."""
    engine = LapKinematicsEngine()
    circuit = CircuitConfig(
        name="Silverstone",
        total_laps=50,
        base_lap_time=90.0,
        fuel_effect_per_lap=0.030,
        track_evolution_per_lap=0.010,
    )
    env = EnvironmentState(lap=1, total_laps=50)

    driver = DriverState(
        driver_id="VER",
        team="Red Bull",
        position=1,
        gap_to_leader=0.0,
        interval_to_ahead=0.0,
        current_compound=TyreCompound.SOFT,
        tyre_age=0,
    )

    state = RaceState(circuit=circuit, environment=env, drivers={"VER": driver})

    # Lap 1:
    # Base: 90.0
    # Deg (Soft, age 0): 0.0
    # Fuel penalty (49 laps remaining * 0.030): 1.47s
    # Rubber benefit (lap 1 * 0.010): -0.01s
    # Total = 90.0 + 1.47 - 0.01 = 91.46s
    lap1_time = engine.calculate_ideal_lap_time(state, driver)
    assert lap1_time == pytest.approx(91.46, abs=1e-3)

    # Move to Lap 40 with 39 laps of tyre wear on Hard tyres
    env.lap = 40
    driver.current_compound = TyreCompound.HARD
    driver.tyre_age = 39

    # Remaining fuel: 10 laps * 0.030 = 0.30s
    # Rubber benefit: 40 * 0.010 = 0.40s
    # Hard base delta + 39 * 0.022 linear deg
    hard_deg = engine.tyre_model.lap_time_penalty(TyreCompound.HARD, 39)
    expected = 90.0 + hard_deg + 0.30 - 0.40
    lap40_time = engine.calculate_ideal_lap_time(state, driver)
    assert lap40_time == pytest.approx(expected, abs=1e-3)


def test_calculate_ideal_lap_time_vsc_and_sc() -> None:
    """Verify VSC and Safety Car speed limiter floor."""
    engine = LapKinematicsEngine()
    circuit = CircuitConfig(name="Monza", total_laps=53, base_lap_time=80.0)
    driver = DriverState(
        driver_id="VER",
        team="Red Bull",
        position=1,
        gap_to_leader=0.0,
        interval_to_ahead=0.0,
        current_compound=TyreCompound.MEDIUM,
    )

    # VSC enforces minimum lap time (1.38x base)
    env_vsc = EnvironmentState(lap=10, total_laps=53, track_status=TrackStatus.VSC)
    state_vsc = RaceState(circuit=circuit, environment=env_vsc, drivers={"VER": driver})
    vsc_lap = engine.calculate_ideal_lap_time(state_vsc, driver)
    assert vsc_lap >= 80.0 * 1.38

    # Safety car enforces minimum lap time (1.55x base)
    env_sc = EnvironmentState(lap=10, total_laps=53, track_status=TrackStatus.SAFETY_CAR)
    state_sc = RaceState(circuit=circuit, environment=env_sc, drivers={"VER": driver})
    sc_lap = engine.calculate_ideal_lap_time(state_sc, driver)
    assert sc_lap >= 80.0 * 1.55


def test_dirty_air_traffic_penalty() -> None:
    """Verify aerodynamic wake dirty air penalties."""
    engine = LapKinematicsEngine()

    # Clean air (> 1.5s interval)
    p_clean = engine.calculate_traffic_penalty(
        circuit_overtaking_difficulty=0.8, interval_to_ahead=2.2
    )
    assert p_clean == 0.0

    # Inside dirty air wake (0.5s interval)
    p_dirty_monaco = engine.calculate_traffic_penalty(
        circuit_overtaking_difficulty=0.95, interval_to_ahead=0.5
    )
    p_dirty_monza = engine.calculate_traffic_penalty(
        circuit_overtaking_difficulty=0.20, interval_to_ahead=0.5
    )

    assert p_dirty_monaco > 0.0
    assert p_dirty_monza > 0.0
    # Dirty air penalty is higher at difficult overtaking circuits
    assert p_dirty_monaco > p_dirty_monza


def test_kinematics_step_forward_simulation() -> None:
    """Verify 1-lap forward simulation step with pit stop execution."""
    engine = LapKinematicsEngine()
    circuit = CircuitConfig(
        name="Silverstone",
        total_laps=50,
        base_lap_time=90.0,
        pit_transit_loss_green=25.0,
    )
    env = EnvironmentState(lap=15, total_laps=50)

    drivers = {
        "VER": DriverState(
            driver_id="VER",
            team="Red Bull",
            position=1,
            gap_to_leader=0.0,
            interval_to_ahead=0.0,
            current_compound=TyreCompound.SOFT,
            tyre_age=15,
            total_race_time=1350.0,
        ),
        "NOR": DriverState(
            driver_id="NOR",
            team="McLaren",
            position=2,
            gap_to_leader=4.0,
            interval_to_ahead=4.0,
            current_compound=TyreCompound.MEDIUM,
            tyre_age=15,
            total_race_time=1354.0,
        ),
    }

    state = RaceState(circuit=circuit, environment=env, drivers=drivers)

    # VER pits for Hard tyres; NOR stays out
    pit_actions = {
        "VER": PitAction(new_compound=TyreCompound.HARD, stationary_duration=2.5),
    }

    next_state = engine.step(state, pit_actions=pit_actions)

    # Lap counter advanced
    assert next_state.environment.lap == 16

    ver = next_state.get_driver("VER")
    nor = next_state.get_driver("NOR")

    # VER executed pit stop: new compound HARD, tyre age reset to 0
    assert ver.current_compound == TyreCompound.HARD
    assert ver.tyre_age == 0
    assert len(ver.pit_stops) == 1
    assert ver.pit_stops[0].compound_in == TyreCompound.SOFT
    assert ver.pit_stops[0].compound_out == TyreCompound.HARD
    assert ver.is_in_pit is True

    # NOR stayed out: tyre age incremented to 16, no pit stop
    assert nor.current_compound == TyreCompound.MEDIUM
    assert nor.tyre_age == 16
    assert len(nor.pit_stops) == 0

    # Because VER lost ~27.5s pitting, NOR should now be in P1, VER in P2!
    assert nor.position == 1
    assert nor.gap_to_leader == 0.0
    assert ver.position == 2
    assert ver.gap_to_leader > 15.0
