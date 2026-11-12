"""Unit tests for race strategy evaluation, stint planning, and 1-stop optimization."""

from __future__ import annotations

import pytest

from stratos.models.pit import TrackStatus
from stratos.models.state import CircuitConfig
from stratos.models.strategy import (
    StintPlan,
    StrategyEvaluator,
    StrategyPlan,
)
from stratos.models.tyre import TyreCompound


def test_stint_plan_validation() -> None:
    """Verify StintPlan lap count validation."""
    stint = StintPlan(compound=TyreCompound.MEDIUM, lap_count=20)
    assert stint.compound == TyreCompound.MEDIUM
    assert stint.lap_count == 20

    with pytest.raises(ValueError, match="lap_count must be >= 1"):
        StintPlan(compound=TyreCompound.MEDIUM, lap_count=0)


def test_strategy_plan_properties() -> None:
    """Verify StrategyPlan properties and FIA dry compliance."""
    # 1-stop strategy: Medium (20) -> Hard (32)
    s1 = StrategyPlan(
        stints=(
            StintPlan(compound=TyreCompound.MEDIUM, lap_count=20),
            StintPlan(compound=TyreCompound.HARD, lap_count=32),
        ),
        name="M-H 1-Stop",
    )
    assert s1.total_laps == 52
    assert s1.pit_stops_count == 1
    assert s1.compounds_used == {TyreCompound.MEDIUM, TyreCompound.HARD}
    assert s1.complies_with_fia_rules(is_wet_race=False)

    # Illegal 0-stop / single compound strategy: Hard (52)
    s_illegal = StrategyPlan(
        stints=(StintPlan(compound=TyreCompound.HARD, lap_count=52),),
        name="No-Stop Hard",
    )
    assert s_illegal.pit_stops_count == 0
    assert not s_illegal.complies_with_fia_rules(is_wet_race=False)
    # But in a wet race, compliance rule is waived
    assert s_illegal.complies_with_fia_rules(is_wet_race=True)


def test_strategy_evaluator_evaluate() -> None:
    """Verify strategy evaluation results and stint timing."""
    circuit = CircuitConfig(
        name="Silverstone",
        total_laps=52,
        base_lap_time=88.0,
        pit_transit_loss_green=25.0,
    )
    evaluator = StrategyEvaluator(circuit)

    plan = StrategyPlan(
        stints=(
            StintPlan(compound=TyreCompound.MEDIUM, lap_count=22),
            StintPlan(compound=TyreCompound.HARD, lap_count=30),
        ),
        name="Medium-Hard 1-Stop",
    )

    result = evaluator.evaluate_strategy(plan, track_temp=35.0)

    assert result.plan is plan
    assert len(result.stint_times) == 2
    assert len(result.lap_times) == 52
    assert result.pit_loss_total == pytest.approx(
        evaluator.pit_loss_model.profile.total_green_pit_loss
    )
    assert result.is_fia_compliant is True
    assert result.total_race_time > 52 * 88.0

    # Total laps mismatch raises ValueError
    bad_plan = StrategyPlan(
        stints=(StintPlan(compound=TyreCompound.MEDIUM, lap_count=10),),
    )
    with pytest.raises(ValueError, match="Strategy total laps .* does not match"):
        evaluator.evaluate_strategy(bad_plan)


def test_strategy_evaluator_vsc_pit_stop() -> None:
    """Verify evaluation under a Virtual Safety Car pit stop."""
    circuit = CircuitConfig(
        name="Monza",
        total_laps=53,
        base_lap_time=81.0,
        pit_transit_loss_green=21.5,
    )
    evaluator = StrategyEvaluator(circuit)

    plan = StrategyPlan(
        stints=(
            StintPlan(compound=TyreCompound.MEDIUM, lap_count=20),
            StintPlan(compound=TyreCompound.HARD, lap_count=33),
        ),
    )

    res_green = evaluator.evaluate_strategy(plan, track_status_per_stop=[TrackStatus.GREEN])
    res_vsc = evaluator.evaluate_strategy(plan, track_status_per_stop=[TrackStatus.VSC])

    # VSC pit stop must be faster than Green flag pit stop
    assert res_vsc.pit_loss_total < res_green.pit_loss_total
    assert res_vsc.total_race_time < res_green.total_race_time


def test_optimize_1stop() -> None:
    """Verify 1-stop pit lap optimization."""
    circuit = CircuitConfig(
        name="Silverstone",
        total_laps=52,
        base_lap_time=88.0,
        pit_transit_loss_green=25.0,
    )
    evaluator = StrategyEvaluator(circuit)

    opt_lap, opt_res = evaluator.optimize_1stop(
        compound1=TyreCompound.MEDIUM,
        compound2=TyreCompound.HARD,
        track_temp=35.0,
    )

    # Optimal lap for Medium -> Hard at Silverstone should fall in mid-race (18-28 laps)
    assert 15 <= opt_lap <= 32
    assert opt_res.total_race_time > 0.0
    assert opt_res.is_fia_compliant is True


def test_compare_strategies() -> None:
    """Verify comparing and ranking multiple candidate strategies."""
    circuit = CircuitConfig(
        name="Silverstone",
        total_laps=52,
        base_lap_time=88.0,
        pit_transit_loss_green=25.0,
    )
    evaluator = StrategyEvaluator(circuit)

    plans = [
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.SOFT, lap_count=16),
                StintPlan(compound=TyreCompound.HARD, lap_count=36),
            ),
            name="Soft -> Hard 1-Stop",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=22),
                StintPlan(compound=TyreCompound.HARD, lap_count=30),
            ),
            name="Medium -> Hard 1-Stop",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.SOFT, lap_count=14),
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=18),
                StintPlan(compound=TyreCompound.HARD, lap_count=20),
            ),
            name="Soft -> Medium -> Hard 2-Stop",
        ),
    ]

    comparisons = evaluator.compare_strategies(plans, track_temp=35.0)

    assert len(comparisons) == 3
    # First item must have delta 0.0 (fastest)
    assert comparisons[0]["delta_to_fastest_seconds"] == 0.0
    # Following items must have non-negative delta
    for c in comparisons[1:]:
        assert c["delta_to_fastest_seconds"] >= 0.0
