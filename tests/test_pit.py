"""Unit tests for pit loss models, circuit pit profiles, and pit window clearance."""

from __future__ import annotations

import pytest

from stratos.models.pit import (
    CIRCUIT_PIT_PROFILES,
    CircuitPitProfile,
    PitLossModel,
    TrackStatus,
)


def test_track_status_parsing() -> None:
    """Verify parsing for TrackStatus strings."""
    assert TrackStatus.from_string("GREEN") == TrackStatus.GREEN
    assert TrackStatus.from_string("clear") == TrackStatus.GREEN
    assert TrackStatus.from_string("YELLOW") == TrackStatus.YELLOW
    assert TrackStatus.from_string("VSC") == TrackStatus.VSC
    assert TrackStatus.from_string("virtual safety car") == TrackStatus.VSC
    assert TrackStatus.from_string("SC") == TrackStatus.SAFETY_CAR
    assert TrackStatus.from_string("safety car") == TrackStatus.SAFETY_CAR
    assert TrackStatus.from_string("RED_FLAG") == TrackStatus.RED_FLAG
    assert TrackStatus.from_string("red") == TrackStatus.RED_FLAG

    with pytest.raises(ValueError, match="Unrecognized track status"):
        TrackStatus.from_string("PURPLE")


def test_circuit_pit_profile_calculations() -> None:
    """Verify nominal pit loss calculations under Green, VSC, and SC."""
    profile = CircuitPitProfile(
        circuit_name="TestCircuit",
        pit_transit_loss_green=20.0,
        typical_stationary_time=2.5,
        vsc_saving_ratio=0.40,
        sc_saving_ratio=0.50,
    )

    # Green = 20.0 + 2.5 = 22.5s
    assert profile.total_green_pit_loss == 22.5
    # VSC = 20.0 * (1 - 0.40) + 2.5 = 12.0 + 2.5 = 14.5s (8.0s saved!)
    assert profile.total_vsc_pit_loss == 14.5
    # SC = 20.0 * (1 - 0.50) + 2.5 = 10.0 + 2.5 = 12.5s (10.0s saved!)
    assert profile.total_sc_pit_loss == 12.5

    assert profile.total_green_pit_loss > profile.total_vsc_pit_loss > profile.total_sc_pit_loss


def test_circuit_registry() -> None:
    """Verify standard profiles for Monaco, Silverstone, Monza, Spa."""
    for circuit_key in ["monaco", "silverstone", "monza", "spa", "red_bull_ring"]:
        assert circuit_key in CIRCUIT_PIT_PROFILES
        p = CIRCUIT_PIT_PROFILES[circuit_key]
        assert p.pit_transit_loss_green > 15.0
        assert p.typical_stationary_time > 1.5


def test_pit_loss_model_conditions() -> None:
    """Verify pit loss model across track conditions and wing changes."""
    model = PitLossModel.for_circuit("Monaco")

    # Green flag
    green_loss = model.calculate_pit_loss(TrackStatus.GREEN)
    assert green_loss == pytest.approx(model.profile.total_green_pit_loss)

    # VSC
    vsc_loss = model.calculate_pit_loss(TrackStatus.VSC)
    assert vsc_loss < green_loss
    assert vsc_loss == pytest.approx(model.profile.total_vsc_pit_loss)

    # Safety Car
    sc_loss = model.calculate_pit_loss(TrackStatus.SAFETY_CAR)
    assert sc_loss < vsc_loss
    assert sc_loss == pytest.approx(model.profile.total_sc_pit_loss)

    # Red Flag (free tyre change during race stoppage)
    red_loss = model.calculate_pit_loss(TrackStatus.RED_FLAG)
    assert red_loss == 0.0

    # Custom stationary time
    custom_loss = model.calculate_pit_loss(TrackStatus.GREEN, stationary_time=3.8)
    assert custom_loss == pytest.approx(model.profile.pit_transit_loss_green + 3.8)

    # Front wing replacement penalty (+8.0 seconds)
    wing_loss = model.calculate_pit_loss(TrackStatus.GREEN, front_wing_change=True)
    assert wing_loss == pytest.approx(green_loss + 8.0)


def test_evaluate_pit_window_traffic_reentry() -> None:
    """Verify pit window clearance and competitor re-entry calculations."""
    model = PitLossModel.for_circuit("Silverstone")
    nominal_loss = model.calculate_pit_loss(TrackStatus.GREEN)  # ~28.0s

    competitors = [
        {"driver_id": "NOR", "position": 2, "gap_to_leader": 5.0},
        {"driver_id": "LEC", "position": 3, "gap_to_leader": 14.0},
        {"driver_id": "HAM", "position": 4, "gap_to_leader": 22.0},
        {"driver_id": "PIA", "position": 5, "gap_to_leader": 32.0},
        {"driver_id": "SAI", "position": 6, "gap_to_leader": 38.0},
    ]

    # Target is leader (gap_to_leader = 0.0)
    # Pitting adds ~28.0s -> Projected gap to leader is ~28.0s
    # In standings:
    # NOR at 5.0s, LEC at 14.0s, HAM at 22.0s -> ahead of pitting driver!
    # PIA at 32.0s -> behind pitting driver!
    # So pitting driver rejoins in P4 (behind NOR, LEC, HAM, ahead of PIA, SAI)
    window = model.evaluate_pit_window(
        target_driver_gap_to_leader=0.0,
        competitor_gaps=competitors,
        track_status=TrackStatus.GREEN,
    )

    assert window["projected_position"] == 4
    assert window["car_ahead"] == "HAM"
    assert window["car_behind"] == "PIA"
    assert window["gap_to_car_ahead"] == pytest.approx(nominal_loss - 22.0)
    assert window["gap_to_car_behind"] == pytest.approx(32.0 - nominal_loss)
    # Gap to HAM is ~6.0s > 1.5s -> clean air
    assert not window["in_traffic"]


def test_evaluate_pit_window_in_traffic() -> None:
    """Verify traffic flag is set when re-entering within 1.5s of car ahead."""
    model = PitLossModel.for_circuit("Monaco")
    loss = model.calculate_pit_loss(TrackStatus.GREEN)

    # Competitor ahead is 23.5s behind leader; pitting leader emerges at loss ~24.2s
    # Gap ahead will be 24.2 - 23.5 = 0.7s < 1.5s (inside turbulent wake)
    competitors = [
        {"driver_id": "ALF", "position": 15, "gap_to_leader": loss - 0.7},
    ]

    window = model.evaluate_pit_window(
        target_driver_gap_to_leader=0.0,
        competitor_gaps=competitors,
        track_status=TrackStatus.GREEN,
    )

    assert window["in_traffic"] is True
    assert window["car_ahead"] == "ALF"
    assert window["gap_to_car_ahead"] == pytest.approx(0.7, abs=1e-3)
