"""Strategy planning, stint evaluation, and pit window optimization.

Evaluates deterministic 1-stop and 2-stop strategies, enforces FIA tyre regulations,
and finds optimal pit windows minimizing total race completion time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from stratos.models.pit import PitLossModel, TrackStatus
from stratos.models.state import CircuitConfig
from stratos.models.tyre import TyreCompound, TyreDegradationModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StintPlan:
    """Individual stint within a race strategy plan.

    Attributes
    ----------
    compound : TyreCompound
        Tyre compound for the stint.
    lap_count : int
        Number of laps to run on this set of tyres.
    """

    compound: TyreCompound
    lap_count: int

    def __post_init__(self) -> None:
        """Validate stint length."""
        if self.lap_count < 1:
            raise ValueError(f"lap_count must be >= 1, got {self.lap_count}")


@dataclass(frozen=True)
class StrategyPlan:
    """Complete race strategy specification comprising multiple sequential stints.

    Attributes
    ----------
    stints : tuple[StintPlan, ...]
        Ordered sequence of stints from race start to chequered flag.
    name : str
        Human-readable descriptor (e.g., 'Medium -> Hard 1-Stop').
    """

    stints: tuple[StintPlan, ...]
    name: str = ""

    @property
    def total_laps(self) -> int:
        """Total race laps scheduled across all stints."""
        return sum(stint.lap_count for stint in self.stints)

    @property
    def pit_stops_count(self) -> int:
        """Total number of pit stops required."""
        return max(0, len(self.stints) - 1)

    @property
    def compounds_used(self) -> set[TyreCompound]:
        """Set of unique compounds used."""
        return {stint.compound for stint in self.stints}

    def complies_with_fia_rules(self, is_wet_race: bool = False) -> bool:
        """Check whether the strategy complies with FIA dry race regulations.

        In dry races, at least two different dry compounds must be used.
        """
        if is_wet_race:
            return True
        dry_compounds = self.compounds_used.intersection(
            {TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD}
        )
        return len(dry_compounds) >= 2


@dataclass
class StrategyEvaluationResult:
    """Evaluation metrics for a strategy plan.

    Attributes
    ----------
    plan : StrategyPlan
        The evaluated strategy plan.
    total_race_time : float
        Simulated total race duration in seconds.
    pit_loss_total : float
        Total time lost across all pit stops.
    stint_times : list[float]
        Time duration (seconds) for each individual stint.
    lap_times : list[float]
        Simulated lap-by-lap time trajectory.
    is_fia_compliant : bool
        Whether the strategy satisfies FIA multi-compound requirements.
    """

    plan: StrategyPlan
    total_race_time: float
    pit_loss_total: float
    stint_times: list[float]
    lap_times: list[float]
    is_fia_compliant: bool


class StrategyEvaluator:
    """Evaluates and compares candidate race strategies."""

    def __init__(
        self,
        circuit: CircuitConfig,
        tyre_model: TyreDegradationModel | None = None,
        pit_loss_model: PitLossModel | None = None,
    ) -> None:
        """Initialize the strategy evaluator.

        Parameters
        ----------
        circuit : CircuitConfig
            Circuit parameters.
        tyre_model : TyreDegradationModel or None
            Tyre degradation model.
        pit_loss_model : PitLossModel or None
            Pit loss model.
        """
        self.circuit = circuit
        self.tyre_model = tyre_model if tyre_model is not None else TyreDegradationModel()
        self.pit_loss_model = (
            pit_loss_model if pit_loss_model is not None else PitLossModel(circuit.to_pit_profile())
        )

    def evaluate_strategy(
        self,
        plan: StrategyPlan,
        track_temp: float = 35.0,
        track_status_per_stop: list[TrackStatus] | None = None,
    ) -> StrategyEvaluationResult:
        """Evaluate expected race duration for a strategy plan in clean air.

        Parameters
        ----------
        plan : StrategyPlan
            Candidate strategy.
        track_temp : float, default 35.0
            Average track surface temperature in °C.
        track_status_per_stop : list[TrackStatus] or None
            Track status under each pit stop (e.g. GREEN, VSC, SAFETY_CAR).

        Returns
        -------
        StrategyEvaluationResult
            Detailed evaluation result.

        Raises
        ------
        ValueError
            If strategy lap total does not match circuit scheduled laps.
        """
        if plan.total_laps != self.circuit.total_laps:
            raise ValueError(
                f"Strategy total laps ({plan.total_laps}) does not match "
                f"circuit total laps ({self.circuit.total_laps})"
            )

        lap_times: list[float] = []
        stint_times: list[float] = []
        pit_loss_total = 0.0

        current_lap = 1
        num_stops = len(plan.stints) - 1

        for stint_idx, stint in enumerate(plan.stints):
            stint_duration = 0.0

            for tyre_age in range(stint.lap_count):
                # Base track time
                t = self.circuit.base_lap_time

                # Compound degradation
                t += self.tyre_model.lap_time_penalty(
                    compound=stint.compound,
                    tyre_age=tyre_age,
                    track_temp=track_temp,
                )

                # Fuel effect (car gets lighter)
                laps_remaining = self.circuit.total_laps - current_lap
                t += laps_remaining * self.circuit.fuel_effect_per_lap

                # Track evolution (rubbering in)
                t -= current_lap * self.circuit.track_evolution_per_lap

                lap_times.append(t)
                stint_duration += t
                current_lap += 1

            # If not the final stint, add pit stop loss
            if stint_idx < num_stops:
                stop_status = (
                    track_status_per_stop[stint_idx]
                    if track_status_per_stop and stint_idx < len(track_status_per_stop)
                    else TrackStatus.GREEN
                )
                stop_loss = self.pit_loss_model.calculate_pit_loss(track_status=stop_status)
                pit_loss_total += stop_loss
                stint_duration += stop_loss

            stint_times.append(stint_duration)

        total_race_time = sum(stint_times)
        is_compliant = plan.complies_with_fia_rules()

        return StrategyEvaluationResult(
            plan=plan,
            total_race_time=float(total_race_time),
            pit_loss_total=float(pit_loss_total),
            stint_times=stint_times,
            lap_times=lap_times,
            is_fia_compliant=is_compliant,
        )

    def optimize_1stop(
        self,
        compound1: TyreCompound | str,
        compound2: TyreCompound | str,
        track_temp: float = 35.0,
    ) -> tuple[int, StrategyEvaluationResult]:
        """Find the optimal pit lap for a 1-stop strategy.

        Sweeps all feasible pit laps and selects the lap minimizing total race time.

        Parameters
        ----------
        compound1 : TyreCompound or str
            Starting compound.
        compound2 : TyreCompound or str
            Second compound.
        track_temp : float
            Track temperature in °C.

        Returns
        -------
        tuple[int, StrategyEvaluationResult]
            Optimal pit lap number and corresponding StrategyEvaluationResult.
        """
        c1 = (
            compound1
            if isinstance(compound1, TyreCompound)
            else TyreCompound.from_string(compound1)
        )
        c2 = (
            compound2
            if isinstance(compound2, TyreCompound)
            else TyreCompound.from_string(compound2)
        )

        total_laps = self.circuit.total_laps
        best_pit_lap = total_laps // 2
        best_result: StrategyEvaluationResult | None = None

        # Sweep valid pit laps (min stint length = 5 laps)
        for pit_lap in range(5, total_laps - 4):
            plan = StrategyPlan(
                stints=(
                    StintPlan(compound=c1, lap_count=pit_lap),
                    StintPlan(compound=c2, lap_count=total_laps - pit_lap),
                ),
                name=f"{c1.value} -> {c2.value} (Pit Lap {pit_lap})",
            )
            result = self.evaluate_strategy(plan, track_temp=track_temp)
            if best_result is None or result.total_race_time < best_result.total_race_time:
                best_result = result
                best_pit_lap = pit_lap

        if best_result is None:
            raise RuntimeError("Optimization failed to evaluate any feasible strategy.")

        return best_pit_lap, best_result

    def compare_strategies(
        self,
        plans: list[StrategyPlan],
        track_temp: float = 35.0,
    ) -> list[dict[str, Any]]:
        """Evaluate and rank candidate strategies by projected race time.

        Parameters
        ----------
        plans : list[StrategyPlan]
            Candidate strategies.
        track_temp : float, default 35.0
            Track temperature in °C.

        Returns
        -------
        list[dict[str, Any]]
            Ranked list of strategy comparisons sorted by fastest race time.
        """
        results: list[dict[str, Any]] = []

        for plan in plans:
            eval_res = self.evaluate_strategy(plan, track_temp=track_temp)
            results.append(
                {
                    "strategy_name": plan.name or " - ".join(s.compound.value for s in plan.stints),
                    "total_time_seconds": eval_res.total_race_time,
                    "pit_stops": plan.pit_stops_count,
                    "pit_loss_seconds": eval_res.pit_loss_total,
                    "is_compliant": eval_res.is_fia_compliant,
                    "stints": [
                        {"compound": s.compound.value, "laps": s.lap_count} for s in plan.stints
                    ],
                }
            )

        results.sort(key=lambda r: r["total_time_seconds"])

        # Add delta to fastest
        fastest_time = results[0]["total_time_seconds"] if results else 0.0
        for r in results:
            r["delta_to_fastest_seconds"] = round(r["total_time_seconds"] - fastest_time, 3)

        return results
