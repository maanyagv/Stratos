"""Unit tests for race state representation, multi-driver grid, and FIA compliance."""

from __future__ import annotations

import pytest

from stratos.models.pit import TrackStatus
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    PitStopRecord,
    RaceState,
)
from stratos.models.tyre import TyreCompound


def test_driver_state_stints_and_compounds() -> None:
    """Verify stint count and compound tracking on DriverState."""
    driver = DriverState(
        driver_id="VER",
        team="Red Bull Racing",
        position=1,
        gap_to_leader=0.0,
        interval_to_ahead=0.0,
        current_compound=TyreCompound.MEDIUM,
    )

    assert driver.stint_number == 1
    assert driver.compounds_used == {TyreCompound.MEDIUM}
    # Only 1 compound used -> FIA dry rule not yet satisfied
    assert not driver.satisfies_two_compound_rule()

    # Add a pit stop to Hard compound
    driver.pit_stops.append(
        PitStopRecord(
            lap=20,
            compound_in=TyreCompound.MEDIUM,
            compound_out=TyreCompound.HARD,
            stationary_duration=2.3,
            total_loss=22.3,
        )
    )
    driver.current_compound = TyreCompound.HARD

    assert driver.stint_number == 2
    assert driver.compounds_used == {TyreCompound.MEDIUM, TyreCompound.HARD}
    # Two distinct dry compounds used -> FIA rule satisfied
    assert driver.satisfies_two_compound_rule()


def test_driver_state_fia_rule_corner_cases() -> None:
    """Verify FIA dry regulation waiver on wet/intermediate tyres."""
    # Two stints on the SAME dry compound (Soft -> Soft): NOT compliant
    d_same = DriverState(
        driver_id="HAM",
        team="Mercedes",
        position=2,
        gap_to_leader=3.0,
        interval_to_ahead=3.0,
        current_compound=TyreCompound.SOFT,
        pit_stops=[
            PitStopRecord(
                lap=15,
                compound_in=TyreCompound.SOFT,
                compound_out=TyreCompound.SOFT,
                stationary_duration=2.5,
                total_loss=23.0,
            )
        ],
    )
    assert not d_same.satisfies_two_compound_rule()

    # Wet tyre used: compliance is waived under FIA regulations
    d_wet = DriverState(
        driver_id="NOR",
        team="McLaren",
        position=3,
        gap_to_leader=5.0,
        interval_to_ahead=2.0,
        current_compound=TyreCompound.INTERMEDIATE,
    )
    assert d_wet.satisfies_two_compound_rule()


def test_circuit_config_and_environment_state() -> None:
    """Verify CircuitConfig and EnvironmentState initialization and helpers."""
    circuit = CircuitConfig(
        name="Monaco",
        total_laps=78,
        base_lap_time=74.5,
        pit_transit_loss_green=21.8,
        overtaking_difficulty=0.95,
    )

    pit_profile = circuit.to_pit_profile()
    assert pit_profile.circuit_name == "Monaco"
    assert pit_profile.pit_transit_loss_green == 21.8

    env = EnvironmentState(
        lap=1,
        total_laps=78,
        track_status=TrackStatus.GREEN,
        track_temp=42.0,
        rainfall_intensity=0.0,
    )
    assert not env.is_wet

    env.rainfall_intensity = 1.2
    assert env.is_wet


def test_race_state_operations() -> None:
    """Verify RaceState queries, standings, and deep cloning."""
    circuit = CircuitConfig(name="Silverstone", total_laps=52, base_lap_time=89.0)
    env = EnvironmentState(lap=10, total_laps=52)

    drivers = {
        "VER": DriverState(
            driver_id="VER",
            team="Red Bull",
            position=1,
            gap_to_leader=0.0,
            interval_to_ahead=0.0,
            current_compound=TyreCompound.MEDIUM,
            tyre_age=10,
        ),
        "NOR": DriverState(
            driver_id="NOR",
            team="McLaren",
            position=2,
            gap_to_leader=3.5,
            interval_to_ahead=3.5,
            current_compound=TyreCompound.MEDIUM,
            tyre_age=10,
        ),
        "LEC": DriverState(
            driver_id="LEC",
            team="Ferrari",
            position=3,
            gap_to_leader=8.2,
            interval_to_ahead=4.7,
            current_compound=TyreCompound.SOFT,
            tyre_age=10,
            is_retired=True,
        ),
    }

    state = RaceState(circuit=circuit, environment=env, drivers=drivers)

    # Driver lookup
    assert state.get_driver("VER").driver_id == "VER"
    with pytest.raises(KeyError, match="Driver 'HAM' not found"):
        state.get_driver("HAM")

    # Leader lookup
    assert state.get_leader().driver_id == "VER"

    # Standings (active first, retired last)
    standings = state.get_standings()
    assert standings[0].driver_id == "VER"
    assert standings[1].driver_id == "NOR"
    assert standings[2].driver_id == "LEC"
    assert standings[2].is_retired is True

    # Pit rejoin projection
    rejoin = state.predict_pit_rejoin("VER")
    assert "projected_position" in rejoin
    assert "car_ahead" in rejoin

    # Deep cloning verification
    cloned = state.clone()
    assert cloned.environment.lap == state.environment.lap
    cloned.environment.lap = 11
    # Original should be untouched
    assert state.environment.lap == 10
    assert cloned.environment.lap == 11
