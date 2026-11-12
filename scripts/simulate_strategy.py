"""Simulate and evaluate Formula 1 race strategies.

Demonstrates tyre degradation models, pit loss analysis under Green vs VSC vs SC,
1-stop pit window optimization, and multi-driver race simulation.

Usage
-----
python scripts/simulate_strategy.py --circuit Silverstone
python scripts/simulate_strategy.py --circuit Monaco --temp 40.0
"""

from __future__ import annotations

import argparse
import logging

from stratos.models.kinematics import LapKinematicsEngine, PitAction
from stratos.models.pit import CIRCUIT_PIT_PROFILES, TrackStatus
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    RaceState,
)
from stratos.models.strategy import (
    StintPlan,
    StrategyEvaluator,
    StrategyPlan,
)
from stratos.models.tyre import (
    DEFAULT_COMPOUND_PARAMS,
    TyreCompound,
    TyreDegradationModel,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("stratos.simulate")


def format_time(seconds: float) -> str:
    """Format total seconds into MM:SS.mmm representation."""
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:06.3f}"


def run_strategy_demo(circuit_name: str, track_temp: float) -> None:
    """Run comprehensive strategy evaluation and simulation."""
    logger.info("=" * 80)
    logger.info(" STRATOS: RACE STRATEGY & STATE MODELING DEMONSTRATION")
    logger.info("=" * 80)

    # 1. Circuit & Pit Profile
    circuit_key = circuit_name.lower().replace(" ", "_")
    profile = CIRCUIT_PIT_PROFILES.get(circuit_key, CIRCUIT_PIT_PROFILES["default"])

    circuit_laps = {
        "monaco": 78,
        "silverstone": 52,
        "monza": 53,
        "spa": 44,
        "red_bull_ring": 71,
    }.get(circuit_key, 52)

    base_time = {
        "monaco": 74.0,
        "silverstone": 88.0,
        "monza": 81.0,
        "spa": 104.0,
        "red_bull_ring": 65.5,
    }.get(circuit_key, 88.0)

    circuit = CircuitConfig(
        name=profile.circuit_name,
        total_laps=circuit_laps,
        base_lap_time=base_time,
        pit_transit_loss_green=profile.pit_transit_loss_green,
        overtaking_difficulty=0.95 if circuit_key == "monaco" else 0.45,
    )

    vsc_saved = profile.total_green_pit_loss - profile.total_vsc_pit_loss
    sc_saved = profile.total_green_pit_loss - profile.total_sc_pit_loss

    logger.info("\n[1] CIRCUIT & PIT LOSS PROFILE")
    logger.info("-" * 80)
    logger.info(
        f"  Circuit: {circuit.name} ({circuit.total_laps} Laps, Base: {circuit.base_lap_time:.2f}s)"
    )
    logger.info(
        f"  Green Flag Pit Loss:  {profile.total_green_pit_loss:.2f}s "
        f"(Transit: {profile.pit_transit_loss_green:.1f}s, "
        f"Box: {profile.typical_stationary_time:.1f}s)"
    )
    logger.info(
        f"  VSC Pit Loss:         {profile.total_vsc_pit_loss:.2f}s (Time Saved: {vsc_saved:.2f}s)"
    )
    logger.info(
        f"  Safety Car Pit Loss:  {profile.total_sc_pit_loss:.2f}s (Time Saved: {sc_saved:.2f}s)"
    )

    # 2. Tyre Degradation Analysis
    tyre_model = TyreDegradationModel()
    logger.info("\n[2] TYRE COMPOUND DEGRADATION CURVES (Track Temp: %.1f°C)", track_temp)
    logger.info("-" * 80)
    hdr = (
        f"  {'Compound':<12} {'Base Delta':<12} {'Linear Deg':<14} "
        f"{'Cliff Lap':<12} {'Lap 10 Deg':<12} {'Lap 25 Deg':<12}"
    )
    logger.info(hdr)
    for comp in [TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD]:
        p = DEFAULT_COMPOUND_PARAMS[comp]
        deg10 = tyre_model.lap_time_penalty(comp, 10, track_temp=track_temp)
        deg25 = tyre_model.lap_time_penalty(comp, 25, track_temp=track_temp)
        row = (
            f"  {comp.value:<12} +{p.base_delta:<11.2f}s +{p.linear_deg:<13.3f}s/l "
            f"{p.cliff_threshold:<12} +{deg10:<11.2f}s +{deg25:<11.2f}s"
        )
        logger.info(row)

    # 3. 1-Stop Optimization
    evaluator = StrategyEvaluator(circuit, tyre_model=tyre_model)
    opt_pit_lap, opt_res = evaluator.optimize_1stop(
        compound1=TyreCompound.MEDIUM,
        compound2=TyreCompound.HARD,
        track_temp=track_temp,
    )
    stint2_laps = circuit.total_laps - opt_pit_lap
    logger.info("\n[3] 1-STOP PIT WINDOW OPTIMIZATION (Medium -> Hard)")
    logger.info("-" * 80)
    logger.info(f"  Optimal Pit Lap: Lap {opt_pit_lap} of {circuit.total_laps}")
    logger.info(
        f"  Total Simulated Race Time: {format_time(opt_res.total_race_time)} "
        f"({opt_res.total_race_time:.2f}s)"
    )
    logger.info(f"  Stint 1 (Medium, {opt_pit_lap} laps): {format_time(opt_res.stint_times[0])}")
    logger.info(f"  Stint 2 (Hard, {stint2_laps} laps):   {format_time(opt_res.stint_times[1])}")

    # 4. Strategy Comparison
    plans = [
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=opt_pit_lap),
                StintPlan(compound=TyreCompound.HARD, lap_count=circuit.total_laps - opt_pit_lap),
            ),
            name="Medium -> Hard (Optimal 1-Stop)",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.SOFT, lap_count=16),
                StintPlan(compound=TyreCompound.HARD, lap_count=circuit.total_laps - 16),
            ),
            name="Soft -> Hard (Aggressive Start 1-Stop)",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.SOFT, lap_count=14),
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=18),
                StintPlan(compound=TyreCompound.HARD, lap_count=circuit.total_laps - 32),
            ),
            name="Soft -> Medium -> Hard (Attack 2-Stop)",
        ),
    ]

    comparisons = evaluator.compare_strategies(plans, track_temp=track_temp)
    logger.info("\n[4] STRATEGY BENCHMARK RANKINGS")
    logger.info("-" * 80)
    cmp_hdr = (
        f"  {'Rank':<5} {'Strategy Name':<38} {'Stops':<6} "
        f"{'Total Time':<12} {'Delta':<10} {'FIA':<5}"
    )
    logger.info(cmp_hdr)
    for idx, c in enumerate(comparisons, 1):
        f_time = format_time(c["total_time_seconds"])
        delta_val = c["delta_to_fastest_seconds"]
        delta_str = f"+{delta_val:.2f}s" if delta_val > 0 else "FASTEST"
        fia_str = "YES" if c["is_compliant"] else "NO"
        s_name = c["strategy_name"]
        stops = c["pit_stops"]
        logger.info(f"  {idx:<5} {s_name:<38} {stops:<6} {f_time:<12} {delta_str:<10} {fia_str:<5}")

    # 5. Multi-Car Forward Step Simulation: Undercut Demonstration
    logger.info("\n[5] LIVE MULTI-CAR UNDERCUT SIMULATION (NOR attacks VER)")
    logger.info("-" * 80)

    drivers = {
        "VER": DriverState(
            driver_id="VER",
            team="Red Bull",
            position=1,
            gap_to_leader=0.0,
            interval_to_ahead=0.0,
            current_compound=TyreCompound.MEDIUM,
            tyre_age=17,
            total_race_time=1500.0,
        ),
        "NOR": DriverState(
            driver_id="NOR",
            team="McLaren",
            position=2,
            gap_to_leader=1.8,
            interval_to_ahead=1.8,
            current_compound=TyreCompound.MEDIUM,
            tyre_age=17,
            total_race_time=1501.8,
        ),
        "LEC": DriverState(
            driver_id="LEC",
            team="Ferrari",
            position=3,
            gap_to_leader=12.0,
            interval_to_ahead=10.2,
            current_compound=TyreCompound.HARD,
            tyre_age=17,
            total_race_time=1512.0,
        ),
    }

    env = EnvironmentState(lap=18, total_laps=circuit.total_laps, track_status=TrackStatus.GREEN)
    race_state = RaceState(circuit=circuit, environment=env, drivers=drivers)
    kinematics = LapKinematicsEngine(tyre_model=tyre_model)

    nor_start_gap = drivers["NOR"].gap_to_leader
    logger.info(f"  Lap 18 Start: VER (P1, M-17), NOR (P2, M-17, Gap: +{nor_start_gap:.2f}s)")
    logger.info("  --> McLaren calls NOR to PIT for fresh HARD tyres (UNDERCUT TRIGGER)!")

    # Lap 18: NOR pits for Hard, VER stays out
    lap18_actions = {"NOR": PitAction(new_compound=TyreCompound.HARD, stationary_duration=2.3)}
    state19 = kinematics.step(race_state, pit_actions=lap18_actions)

    ver19 = state19.get_driver("VER")
    nor19 = state19.get_driver("NOR")
    logger.info(
        f"  Lap 19: VER stayed out (Lap Time: {ver19.last_lap_time:.2f}s). "
        f"NOR pitted (In-pit lap: {nor19.last_lap_time:.2f}s). "
        f"NOR gap to VER: +{nor19.gap_to_leader:.2f}s"
    )

    # Lap 19: NOR has fresh tyres on clean out-lap; VER stays out on 19-lap old mediums
    state20 = kinematics.step(state19, pit_actions=None)
    ver20 = state20.get_driver("VER")
    nor20 = state20.get_driver("NOR")
    assert ver20.last_lap_time is not None and nor20.last_lap_time is not None
    pace_delta = ver20.last_lap_time - nor20.last_lap_time
    logger.info(
        f"  Lap 20: NOR flying lap ({nor20.last_lap_time:.2f}s) vs "
        f"VER degraded lap ({ver20.last_lap_time:.2f}s). NOR gained {pace_delta:.2f}s!"
    )

    # Lap 20: Red Bull responds, pitting VER
    logger.info("  --> Red Bull reacts: VER pits on Lap 20!")
    lap20_actions = {"VER": PitAction(new_compound=TyreCompound.HARD, stationary_duration=2.4)}
    state21 = kinematics.step(state20, pit_actions=lap20_actions)

    standings = state21.get_standings()
    logger.info("\n  Race Standings After Pit Stops (Lap 21):")
    for d in standings:
        logger.info(
            f"    P{d.position}: {d.driver_id} ({d.team}) | Gap: +{d.gap_to_leader:.2f}s | "
            f"Tyre: {d.current_compound.value} (Age: {d.tyre_age}) | Stops: {len(d.pit_stops)}"
        )

    if standings[0].driver_id == "NOR":
        logger.info("\n  RESULT: UNDERCUT SUCCESSFUL! NOR takes the lead from VER.")
    else:
        logger.info("\n  RESULT: VER retained the lead.")

    logger.info("=" * 80)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="STRATOS Race Strategy Simulation & Evaluation")
    parser.add_argument(
        "--circuit",
        type=str,
        default="Silverstone",
        help="Circuit name (e.g. Monaco, Silverstone, Monza, Spa)",
    )
    parser.add_argument(
        "--temp",
        type=float,
        default=35.0,
        help="Track temperature in °C (default 35.0)",
    )
    args = parser.parse_args()

    run_strategy_demo(args.circuit, args.temp)


if __name__ == "__main__":
    main()
