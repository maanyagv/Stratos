"""Unit tests for tyre degradation, compound modeling, and telemetry fitting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stratos.models.tyre import (
    DEFAULT_COMPOUND_PARAMS,
    TyreCompound,
    TyreDegradationModel,
    TyreParameters,
    fit_degradation_from_laps,
)


def test_tyre_compound_from_string() -> None:
    """Verify string parsing for tyre compounds."""
    assert TyreCompound.from_string("soft") == TyreCompound.SOFT
    assert TyreCompound.from_string("S") == TyreCompound.SOFT
    assert TyreCompound.from_string("MEDIUM") == TyreCompound.MEDIUM
    assert TyreCompound.from_string("m") == TyreCompound.MEDIUM
    assert TyreCompound.from_string("HARD") == TyreCompound.HARD
    assert TyreCompound.from_string("H") == TyreCompound.HARD
    assert TyreCompound.from_string("INTERMEDIATE") == TyreCompound.INTERMEDIATE
    assert TyreCompound.from_string("inter") == TyreCompound.INTERMEDIATE
    assert TyreCompound.from_string("wet") == TyreCompound.WET
    assert TyreCompound.from_string("W") == TyreCompound.WET

    with pytest.raises(ValueError, match="Unrecognized tyre compound"):
        TyreCompound.from_string("HYPERSOFT")


def test_tyre_parameters_validation() -> None:
    """Verify validation on TyreParameters dataclass."""
    with pytest.raises(ValueError, match="base_delta must be non-negative"):
        TyreParameters(compound=TyreCompound.SOFT, base_delta=-0.5, linear_deg=0.05)

    with pytest.raises(ValueError, match="linear_deg must be non-negative"):
        TyreParameters(compound=TyreCompound.SOFT, base_delta=0.0, linear_deg=-0.01)

    with pytest.raises(ValueError, match="cliff_threshold must be >= 1"):
        TyreParameters(
            compound=TyreCompound.SOFT, base_delta=0.0, linear_deg=0.05, cliff_threshold=0
        )

    with pytest.raises(ValueError, match="optimal_temp_min .* strictly less than optimal_temp_max"):
        TyreParameters(
            compound=TyreCompound.SOFT,
            base_delta=0.0,
            linear_deg=0.05,
            optimal_temp_min=50.0,
            optimal_temp_max=40.0,
        )


def test_default_compound_parameters_coverage() -> None:
    """Verify that default compound parameters cover all dry and wet compounds."""
    for comp in TyreCompound:
        assert comp in DEFAULT_COMPOUND_PARAMS
        params = DEFAULT_COMPOUND_PARAMS[comp]
        assert params.base_delta >= 0.0
        assert params.linear_deg > 0.0


def test_tyre_degradation_model_lap_penalties() -> None:
    """Verify lap time penalties across tyre age and compounds."""
    model = TyreDegradationModel()

    # Lap 0: penalty equals base delta
    assert model.lap_time_penalty(TyreCompound.SOFT, 0) == pytest.approx(0.00, abs=1e-4)
    assert model.lap_time_penalty(TyreCompound.MEDIUM, 0) == pytest.approx(0.55, abs=1e-4)
    assert model.lap_time_penalty(TyreCompound.HARD, 0) == pytest.approx(1.15, abs=1e-4)

    # Linear wear: Soft at lap 10 = 0.00 + 10 * 0.085 = 0.85
    soft_p10 = model.lap_time_penalty(TyreCompound.SOFT, 10)
    assert soft_p10 == pytest.approx(0.85, abs=1e-4)

    # Negative age check
    with pytest.raises(ValueError, match="tyre_age must be non-negative"):
        model.lap_time_penalty(TyreCompound.SOFT, -1)


def test_tyre_cliff_behavior() -> None:
    """Verify non-linear degradation beyond cliff threshold."""
    model = TyreDegradationModel()
    params = model.get_parameters(TyreCompound.SOFT)

    # Below cliff
    assert not model.is_cliff_exceeded(TyreCompound.SOFT, params.cliff_threshold)
    # Above cliff
    assert model.is_cliff_exceeded(TyreCompound.SOFT, params.cliff_threshold + 1)

    penalty_at_cliff = model.lap_time_penalty(TyreCompound.SOFT, params.cliff_threshold)
    penalty_past_cliff = model.lap_time_penalty(TyreCompound.SOFT, params.cliff_threshold + 5)

    # Linear delta for 5 laps is 5 * 0.085 = 0.425
    linear_gain = 5 * params.linear_deg
    nonlinear_gain = penalty_past_cliff - (penalty_at_cliff + linear_gain)
    assert nonlinear_gain > 0.0  # Non-linear cliff penalty must add additional wear


def test_thermal_operating_window_penalties() -> None:
    """Verify temperature penalties outside optimal operating window."""
    model = TyreDegradationModel()
    params = model.get_parameters(TyreCompound.MEDIUM)

    # Within optimal window [25.0, 42.0]
    p_opt = model.lap_time_penalty(TyreCompound.MEDIUM, tyre_age=5, track_temp=30.0)
    # Cold track (20°C is 5°C below min 25.0°C)
    p_cold = model.lap_time_penalty(TyreCompound.MEDIUM, tyre_age=5, track_temp=20.0)
    # Overheated track (50°C is 8°C above max 42.0°C)
    p_hot = model.lap_time_penalty(TyreCompound.MEDIUM, tyre_age=5, track_temp=50.0)

    assert p_cold > p_opt
    assert p_cold == pytest.approx(p_opt + 5.0 * params.temp_sensitivity, abs=1e-4)
    assert p_hot > p_opt
    assert p_hot == pytest.approx(p_opt + 8.0 * params.temp_sensitivity, abs=1e-4)


def test_simulate_stint() -> None:
    """Verify stint simulation sequence."""
    model = TyreDegradationModel()
    stint_penalties = model.simulate_stint(TyreCompound.HARD, stint_length=20)

    assert len(stint_penalties) == 20
    # Degradation must be strictly monotonically increasing with age
    for i in range(1, len(stint_penalties)):
        assert stint_penalties[i] > stint_penalties[i - 1]

    with pytest.raises(ValueError, match="stint_length must be >= 1"):
        model.simulate_stint(TyreCompound.HARD, stint_length=0)


def test_custom_parameters_override() -> None:
    """Verify setting custom compound parameters in the model."""
    model = TyreDegradationModel()
    custom_params = TyreParameters(
        compound=TyreCompound.SOFT,
        base_delta=0.0,
        linear_deg=0.120,  # High degradation circuit
        cliff_threshold=12,
    )
    model.set_parameters(TyreCompound.SOFT, custom_params)
    assert model.get_parameters(TyreCompound.SOFT).linear_deg == 0.120

    with pytest.raises(ValueError, match="Parameter compound .* does not match"):
        model.set_parameters(TyreCompound.HARD, custom_params)


def test_fit_degradation_from_synthetic_laps() -> None:
    """Verify regression fitting from clean lap timing telemetry."""
    # Synthesize clean laps for Medium tyres: LapTime = 80.0 + 0.05 * TyreLife - 0.033 * TyreLife
    np.random.seed(42)
    tyre_lifes = np.arange(1, 26)
    true_base = 80.0
    true_deg = 0.050
    fuel_corr = 0.033

    # On track, lap times decrease due to fuel burn but increase due to tyre deg
    lap_times = (
        true_base + (true_deg - fuel_corr) * tyre_lifes + np.random.normal(0, 0.05, len(tyre_lifes))
    )

    df = pd.DataFrame(
        {
            "LapNumber": tyre_lifes,
            "TyreLife": tyre_lifes,
            "Compound": ["MEDIUM"] * len(tyre_lifes),
            "LapTime": lap_times,
            "PitInTime": [np.nan] * len(tyre_lifes),
            "PitOutTime": [np.nan] * len(tyre_lifes),
        }
    )

    fit_res = fit_degradation_from_laps(df, compound="MEDIUM", fuel_correction_per_lap=fuel_corr)

    assert fit_res["compound"] == TyreCompound.MEDIUM
    assert fit_res["sample_count"] == 25
    assert fit_res["r_squared"] > 0.85
    # Fitted linear deg should recover true_deg (~0.050)
    assert fit_res["linear_deg"] == pytest.approx(true_deg, abs=0.015)


def test_fit_degradation_insufficient_data() -> None:
    """Verify ValueError is raised if insufficient laps are present."""
    df = pd.DataFrame(
        {
            "Compound": ["SOFT", "SOFT"],
            "LapTime": [85.0, 85.2],
            "TyreLife": [1, 2],
        }
    )
    with pytest.raises(ValueError, match="Insufficient clean laps"):
        fit_degradation_from_laps(df, compound="SOFT", min_samples=5)
