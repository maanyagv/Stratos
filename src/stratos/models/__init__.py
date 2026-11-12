"""Models package for STRATOS.

Provides state representation, kinematics, tyre degradation, and pit deltas.
"""

from __future__ import annotations

from stratos.models.kinematics import LapKinematicsEngine, PitAction
from stratos.models.pit import (
    CIRCUIT_PIT_PROFILES,
    CircuitPitProfile,
    PitLossModel,
    TrackStatus,
)
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    PitStopRecord,
    RaceState,
)
from stratos.models.strategy import (
    StintPlan,
    StrategyEvaluationResult,
    StrategyEvaluator,
    StrategyPlan,
)
from stratos.models.tyre import (
    DEFAULT_COMPOUND_PARAMS,
    TyreCompound,
    TyreDegradationModel,
    TyreParameters,
    fit_degradation_from_laps,
)

__all__ = [
    # Tyre
    "TyreCompound",
    "TyreParameters",
    "DEFAULT_COMPOUND_PARAMS",
    "TyreDegradationModel",
    "fit_degradation_from_laps",
    # Pit
    "TrackStatus",
    "CircuitPitProfile",
    "CIRCUIT_PIT_PROFILES",
    "PitLossModel",
    # State
    "PitStopRecord",
    "DriverState",
    "CircuitConfig",
    "EnvironmentState",
    "RaceState",
    # Kinematics
    "PitAction",
    "LapKinematicsEngine",
    # Strategy
    "StintPlan",
    "StrategyPlan",
    "StrategyEvaluationResult",
    "StrategyEvaluator",
]
