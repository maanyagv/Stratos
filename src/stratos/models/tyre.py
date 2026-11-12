"""Tyre degradation and compound modeling for Formula 1 race strategy.

This module provides physical and empirical tyre degradation models, compound
parameterizations (Soft, Medium, Hard, Intermediate, Wet), thermal sensitivity,
and regression utilities for fitting wear rates from historical telemetry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TyreCompound(StrEnum):
    """Formula 1 tyre compounds."""

    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"

    @classmethod
    def from_string(cls, value: str) -> TyreCompound:
        """Parse compound string case-insensitively.

        Parameters
        ----------
        value : str
            Compound name (e.g., 'SOFT', 'soft', 'S', 'MEDIUM', 'M').

        Returns
        -------
        TyreCompound
            Matching TyreCompound enum member.

        Raises
        ------
        ValueError
            If the compound name cannot be resolved.
        """
        normalized = value.strip().upper()
        shorthand_map = {
            "S": cls.SOFT,
            "SOFT": cls.SOFT,
            "M": cls.MEDIUM,
            "MEDIUM": cls.MEDIUM,
            "H": cls.HARD,
            "HARD": cls.HARD,
            "I": cls.INTERMEDIATE,
            "INTER": cls.INTERMEDIATE,
            "INTERMEDIATE": cls.INTERMEDIATE,
            "W": cls.WET,
            "WET": cls.WET,
        }
        if normalized in shorthand_map:
            return shorthand_map[normalized]
        raise ValueError(
            f"Unrecognized tyre compound '{value}'. Valid options: {[c.value for c in cls]}"
        )


@dataclass(frozen=True)
class TyreParameters:
    """Kinematic and degradation parameters for a specific tyre compound.

    Attributes
    ----------
    compound : TyreCompound
        The tyre compound type.
    base_delta : float
        Lap time offset (seconds) at age 0 relative to Soft compound baseline (0.0s).
    linear_deg : float
        Linear degradation coefficient (seconds added per completed lap).
    nonlinear_deg : float
        Nonlinear penalty coefficient applied beyond the cliff threshold.
    cliff_threshold : int
        Lap age at which severe non-linear tyre cliff degradation begins.
    cliff_exponent : float
        Exponential factor governing wear escalation beyond the cliff.
    optimal_temp_min : float
        Minimum track temperature (°C) for the compound's optimal operating window.
    optimal_temp_max : float
        Maximum track temperature (°C) for the compound's optimal operating window.
    temp_sensitivity : float
        Penalty in seconds per degree Celsius when operating outside the optimal window.
    """

    compound: TyreCompound
    base_delta: float
    linear_deg: float
    nonlinear_deg: float = 0.002
    cliff_threshold: int = 24
    cliff_exponent: float = 2.0
    optimal_temp_min: float = 25.0
    optimal_temp_max: float = 45.0
    temp_sensitivity: float = 0.015

    def __post_init__(self) -> None:
        """Validate tyre parameters."""
        if self.base_delta < 0.0:
            raise ValueError(f"base_delta must be non-negative, got {self.base_delta}")
        if self.linear_deg < 0.0:
            raise ValueError(f"linear_deg must be non-negative, got {self.linear_deg}")
        if self.cliff_threshold < 1:
            raise ValueError(f"cliff_threshold must be >= 1, got {self.cliff_threshold}")
        if self.optimal_temp_min >= self.optimal_temp_max:
            raise ValueError(
                f"optimal_temp_min ({self.optimal_temp_min}) must be strictly less "
                f"than optimal_temp_max ({self.optimal_temp_max})"
            )


# Default calibrated parameter sets based on typical modern F1 dry/wet compounds
DEFAULT_COMPOUND_PARAMS: dict[TyreCompound, TyreParameters] = {
    TyreCompound.SOFT: TyreParameters(
        compound=TyreCompound.SOFT,
        base_delta=0.00,  # Benchmark fastest initial pace
        linear_deg=0.085,  # ~0.085s wear per lap
        nonlinear_deg=0.004,
        cliff_threshold=18,  # Deg cliff hits after ~18 laps
        cliff_exponent=2.0,
        optimal_temp_min=30.0,
        optimal_temp_max=45.0,
        temp_sensitivity=0.020,
    ),
    TyreCompound.MEDIUM: TyreParameters(
        compound=TyreCompound.MEDIUM,
        base_delta=0.55,  # ~0.55s slower than Soft at lap 0
        linear_deg=0.045,  # ~0.045s wear per lap
        nonlinear_deg=0.002,
        cliff_threshold=28,  # Deg cliff hits after ~28 laps
        cliff_exponent=2.0,
        optimal_temp_min=25.0,
        optimal_temp_max=42.0,
        temp_sensitivity=0.015,
    ),
    TyreCompound.HARD: TyreParameters(
        compound=TyreCompound.HARD,
        base_delta=1.15,  # ~1.15s slower than Soft at lap 0
        linear_deg=0.022,  # ~0.022s wear per lap
        nonlinear_deg=0.0008,
        cliff_threshold=44,  # Deg cliff hits after ~44 laps
        cliff_exponent=2.0,
        optimal_temp_min=20.0,
        optimal_temp_max=40.0,
        temp_sensitivity=0.010,
    ),
    TyreCompound.INTERMEDIATE: TyreParameters(
        compound=TyreCompound.INTERMEDIATE,
        base_delta=4.50,  # Lap delta under dry conditions
        linear_deg=0.250,  # Fast degradation on drying tracks
        nonlinear_deg=0.010,
        cliff_threshold=25,
        cliff_exponent=2.0,
        optimal_temp_min=15.0,
        optimal_temp_max=32.0,
        temp_sensitivity=0.030,
    ),
    TyreCompound.WET: TyreParameters(
        compound=TyreCompound.WET,
        base_delta=9.00,  # Lap delta under dry conditions
        linear_deg=0.350,
        nonlinear_deg=0.015,
        cliff_threshold=30,
        cliff_exponent=2.0,
        optimal_temp_min=10.0,
        optimal_temp_max=28.0,
        temp_sensitivity=0.040,
    ),
}


class TyreDegradationModel:
    """Degradation model evaluating pace degradation over tyre stint lifetime.

    Supports linear wear, non-linear cliff penalties, and thermal operating window
    deviations.
    """

    def __init__(
        self,
        parameters: dict[TyreCompound, TyreParameters] | None = None,
    ) -> None:
        """Initialize the tyre degradation model.

        Parameters
        ----------
        parameters : dict[TyreCompound, TyreParameters] or None
            Compound parameters dictionary. If None, uses DEFAULT_COMPOUND_PARAMS.
        """
        self._params: dict[TyreCompound, TyreParameters] = (
            parameters.copy() if parameters is not None else DEFAULT_COMPOUND_PARAMS.copy()
        )

    def get_parameters(self, compound: TyreCompound | str) -> TyreParameters:
        """Retrieve parameters for a given compound.

        Parameters
        ----------
        compound : TyreCompound or str
            Tyre compound.

        Returns
        -------
        TyreParameters
            Calibrated parameter set for the compound.
        """
        comp = (
            compound if isinstance(compound, TyreCompound) else TyreCompound.from_string(compound)
        )
        if comp not in self._params:
            raise KeyError(f"No parameters configured for compound '{comp.value}'.")
        return self._params[comp]

    def set_parameters(self, compound: TyreCompound, parameters: TyreParameters) -> None:
        """Set or update parameters for a specific compound.

        Parameters
        ----------
        compound : TyreCompound
            Target compound.
        parameters : TyreParameters
            New parameters.
        """
        if parameters.compound != compound:
            raise ValueError(
                f"Parameter compound '{parameters.compound}' does not match key '{compound}'"
            )
        self._params[compound] = parameters

    def lap_time_penalty(
        self,
        compound: TyreCompound | str,
        tyre_age: int,
        track_temp: float | None = None,
    ) -> float:
        """Calculate the total lap time degradation penalty in seconds.

        The total tyre penalty consists of:
          1. Base compound offset at age 0.
          2. Linear degradation proportional to tyre age.
          3. Non-linear degradation cliff penalty when age exceeds cliff threshold.
          4. Thermal penalty if track temperature is outside the optimal operating window.

        Parameters
        ----------
        compound : TyreCompound or str
            Tyre compound.
        tyre_age : int
            Completed laps on current set of tyres (must be >= 0).
        track_temp : float or None, default None
            Track temperature in degrees Celsius. If None, assumed within optimal window.

        Returns
        -------
        float
            Total lap time penalty in seconds.

        Raises
        ------
        ValueError
            If tyre_age is negative.
        """
        if tyre_age < 0:
            raise ValueError(f"tyre_age must be non-negative, got {tyre_age}")

        params = self.get_parameters(compound)

        # 1. Base compound delta
        penalty = params.base_delta

        # 2. Linear wear
        penalty += params.linear_deg * tyre_age

        # 3. Non-linear cliff penalty
        if tyre_age > params.cliff_threshold:
            excess_laps = tyre_age - params.cliff_threshold
            penalty += params.nonlinear_deg * (excess_laps**params.cliff_exponent)

        # 4. Thermal penalty
        if track_temp is not None:
            if track_temp < params.optimal_temp_min:
                temp_delta = params.optimal_temp_min - track_temp
                penalty += params.temp_sensitivity * temp_delta
            elif track_temp > params.optimal_temp_max:
                temp_delta = track_temp - params.optimal_temp_max
                penalty += params.temp_sensitivity * temp_delta

        return float(penalty)

    def is_cliff_exceeded(self, compound: TyreCompound | str, tyre_age: int) -> bool:
        """Check whether the given tyre has exceeded its degradation cliff threshold.

        Parameters
        ----------
        compound : TyreCompound or str
            Tyre compound.
        tyre_age : int
            Laps completed on current set.

        Returns
        -------
        bool
            True if tyre_age > cliff_threshold, False otherwise.
        """
        params = self.get_parameters(compound)
        return tyre_age > params.cliff_threshold

    def simulate_stint(
        self,
        compound: TyreCompound | str,
        stint_length: int,
        track_temp: float | None = None,
    ) -> list[float]:
        """Simulate cumulative lap time degradation penalties across a stint.

        Parameters
        ----------
        compound : TyreCompound or str
            Tyre compound.
        stint_length : int
            Total number of laps in the stint (must be >= 1).
        track_temp : float or None, default None
            Track temperature in °C.

        Returns
        -------
        list[float]
            List of lap time penalties (seconds) for each lap in the stint.
        """
        if stint_length < 1:
            raise ValueError(f"stint_length must be >= 1, got {stint_length}")

        return [
            self.lap_time_penalty(compound, age, track_temp=track_temp)
            for age in range(stint_length)
        ]


def fit_degradation_from_laps(
    laps_df: pd.DataFrame,
    compound: TyreCompound | str,
    fuel_correction_per_lap: float = 0.033,
    min_samples: int = 5,
) -> dict[str, Any]:
    """Fit empirical linear degradation parameters from historical clean race laps.

    Parameters
    ----------
    laps_df : pd.DataFrame
        DataFrame containing FastF1-style laps with columns:
        'LapTime', 'Compound', 'TyreLife', and optional 'TrackStatus' / 'PitOutTime'.
    compound : TyreCompound or str
        Compound to isolate and fit.
    fuel_correction_per_lap : float, default 0.033
        Fuel burn-off lap time advantage in seconds per lap. Adding this back
        isolates true rubber wear from fuel-lightening effects.
    min_samples : int, default 5
        Minimum number of valid laps required for regression.

    Returns
    -------
    dict[str, Any]
        Dictionary with fitted parameters:
        - 'compound': TyreCompound
        - 'base_time_seconds': float
        - 'linear_deg': float (seconds per lap)
        - 'r_squared': float
        - 'sample_count': int

    Raises
    ------
    ValueError
        If insufficient clean laps are available for fitting.
    """
    comp = compound if isinstance(compound, TyreCompound) else TyreCompound.from_string(compound)

    if "Compound" not in laps_df.columns or "LapTime" not in laps_df.columns:
        raise ValueError("laps_df must contain 'Compound' and 'LapTime' columns")

    # Filter by compound
    mask = laps_df["Compound"].astype(str).str.upper() == comp.value
    subset = laps_df[mask].copy()

    if "TyreLife" not in subset.columns:
        if "LapNumber" in subset.columns:
            subset["TyreLife"] = subset["LapNumber"]
        else:
            raise ValueError("laps_df must contain 'TyreLife' or 'LapNumber' column")

    # Clean lap time to seconds
    if pd.api.types.is_timedelta64_dtype(subset["LapTime"]):
        subset["LapTimeSec"] = subset["LapTime"].dt.total_seconds()
    else:
        subset["LapTimeSec"] = pd.to_numeric(subset["LapTime"], errors="coerce")

    # Drop NaNs and invalid times
    valid = subset.dropna(subset=["LapTimeSec", "TyreLife"])

    # Remove pit-in / pit-out laps if indicators are present
    if "PitInTime" in valid.columns:
        valid = valid[valid["PitInTime"].isna()]
    if "PitOutTime" in valid.columns:
        valid = valid[valid["PitOutTime"].isna()]

    # Filter out slow outliers (>107% of median lap time)
    if len(valid) > 0:
        median_time = valid["LapTimeSec"].median()
        valid = valid[valid["LapTimeSec"] <= median_time * 1.07]

    if len(valid) < min_samples:
        raise ValueError(
            f"Insufficient clean laps ({len(valid)} found, minimum {min_samples} required) "
            f"for compound '{comp.value}'."
        )

    # Correct for fuel burn (fuel makes car faster over time, masking tyre deg)
    # Corrected time = LapTimeSec + (TyreLife * fuel_correction_per_lap)
    x = valid["TyreLife"].values.astype(float)
    y = valid["LapTimeSec"].values.astype(float) + (x * fuel_correction_per_lap)

    # Perform linear regression
    slope, intercept = np.polyfit(x, y, deg=1)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return {
        "compound": comp,
        "base_time_seconds": float(intercept),
        "linear_deg": max(0.0, float(slope)),
        "r_squared": float(r2),
        "sample_count": int(len(valid)),
    }
