"""Run STRATOS deliberative multi-agent strategy team on realistic race scenarios.

Demonstrates:
  1. Undercut Attack (Silverstone)
  2. Traffic Dilemma & Re-entry Arbitration (Monaco)
  3. Meteorological Rain Crossover (Spa)
  4. Safety Car Golden Window (Monza)

Usage
-----
python scripts/run_agents.py --scenario all
python scripts/run_agents.py --scenario undercut
python scripts/run_agents.py --scenario rain
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from stratos.agents.team import STRATOSStrategyTeam
from stratos.models.pit import TrackStatus
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    RaceState,
)
from stratos.models.tyre import TyreCompound

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("stratos.agents_demo")


def print_synthesis_banner(scenario_name: str, circuit: str, lap: int) -> None:
    """Print header banner for a scenario."""
    logger.info("\n" + "=" * 80)
    logger.info(f" SCENARIO: {scenario_name.upper()} ({circuit} - Lap {lap})")
    logger.info("=" * 80)


def print_synthesis_result(synthesis: Any) -> None:
    """Pretty-print deliberative agent synthesis."""
    logger.info("\n[1] SPECIALIST AGENT DELIBERATION REPORTS:")
    logger.info("-" * 80)
    for agent_name, report in synthesis.agent_reports.items():
        logger.info(
            f"  {agent_name:<24} | Action: {report.recommendation.value:<22} | "
            f"Urgency: {report.urgency.value:<8} | Risk: {report.risk_score:.2f} | "
            f"Conf: {report.confidence:.2f}"
        )
        logger.info(f"    --> Rationale: {report.rationale}")

    logger.info("\n[2] LEAD STRATEGIST CONSENSUS DIRECTIVE:")
    logger.info("-" * 80)
    comp_str = synthesis.chosen_compound.value if synthesis.chosen_compound else "N/A"
    logger.info(f"  Target Driver      : {synthesis.target_driver}")
    logger.info(f"  Primary Action     : {synthesis.primary_action.value}")
    logger.info(f"  Chosen Compound    : {comp_str}")
    logger.info(f"  Urgency Level      : {synthesis.urgency.value}")
    logger.info(f"  Composite Risk     : {synthesis.composite_risk:.2f}")
    logger.info(f"  Synthesis Conf     : {synthesis.confidence:.2f}")
    logger.info(f'  Radio Call Command : "{synthesis.executive_summary}"')
    logger.info("\n[3] DELIBERATIVE ARBITRATION RATIONALE:")
    logger.info(f"  {synthesis.deliberative_rationale}")
    logger.info("=" * 80)


def run_undercut_scenario() -> None:
    """Scenario 1: Undercut strike opportunity at Silverstone."""
    print_synthesis_banner("Undercut Attack Opportunity", "Silverstone", lap=18)
    circuit = CircuitConfig(
        name="Silverstone",
        total_laps=52,
        base_lap_time=88.0,
        pit_transit_loss_green=25.6,
        overtaking_difficulty=0.45,
    )
    env = EnvironmentState(lap=18, total_laps=52, track_status=TrackStatus.GREEN)
    drivers = {
        "VER": DriverState("VER", "Red Bull", 1, 0.0, 0.0, TyreCompound.MEDIUM, tyre_age=18),
        "NOR": DriverState("NOR", "McLaren", 2, 1.8, 1.8, TyreCompound.MEDIUM, tyre_age=18),
        "LEC": DriverState("LEC", "Ferrari", 3, 14.0, 12.2, TyreCompound.HARD, tyre_age=18),
    }
    state = RaceState(circuit, env, drivers)
    team = STRATOSStrategyTeam()
    synthesis = team.evaluate_turn(state, "NOR")
    print_synthesis_result(synthesis)


def run_monaco_traffic_scenario() -> None:
    """Scenario 2: Monaco undercut aborted due to traffic re-entry in dirty air."""
    print_synthesis_banner("Traffic Dilemma & Arbitration", "Monaco", lap=22)
    circuit = CircuitConfig(
        name="Monaco",
        total_laps=78,
        base_lap_time=74.0,
        pit_transit_loss_green=21.8,
        overtaking_difficulty=0.95,
    )
    env = EnvironmentState(lap=22, total_laps=78, track_status=TrackStatus.GREEN)
    drivers = {
        "VER": DriverState("VER", "Red Bull", 1, 0.0, 0.0, TyreCompound.MEDIUM, tyre_age=22),
        "NOR": DriverState("NOR", "McLaren", 2, 1.8, 1.8, TyreCompound.MEDIUM, tyre_age=22),
        "BOT": DriverState("BOT", "Sauber", 15, 25.4, 1.0, TyreCompound.HARD, tyre_age=22),
    }
    state = RaceState(circuit, env, drivers)
    team = STRATOSStrategyTeam()
    synthesis = team.evaluate_turn(state, "NOR")
    print_synthesis_result(synthesis)


def run_rain_scenario() -> None:
    """Scenario 3: Meteorological rain crossover at Spa."""
    print_synthesis_banner("Meteorological Rain Crossover", "Spa-Francorchamps", lap=15)
    circuit = CircuitConfig(
        name="Spa-Francorchamps",
        total_laps=44,
        base_lap_time=104.0,
        pit_transit_loss_green=19.2,
        overtaking_difficulty=0.35,
    )
    env = EnvironmentState(
        lap=15,
        total_laps=44,
        track_status=TrackStatus.GREEN,
        rainfall_intensity=0.85,  # Crossing intermediate threshold (0.3 mm/h)
    )
    drivers = {
        "VER": DriverState("VER", "Red Bull", 1, 0.0, 0.0, TyreCompound.MEDIUM, tyre_age=15),
        "NOR": DriverState("NOR", "McLaren", 2, 4.2, 4.2, TyreCompound.MEDIUM, tyre_age=15),
    }
    state = RaceState(circuit, env, drivers)
    team = STRATOSStrategyTeam()
    synthesis = team.evaluate_turn(state, "VER")
    print_synthesis_result(synthesis)


def run_safety_car_scenario() -> None:
    """Scenario 4: Safety Car golden pit window at Monza."""
    print_synthesis_banner("Safety Car Golden Window", "Monza", lap=24)
    circuit = CircuitConfig(
        name="Monza",
        total_laps=53,
        base_lap_time=81.0,
        pit_transit_loss_green=21.5,
        overtaking_difficulty=0.25,
    )
    env = EnvironmentState(
        lap=24,
        total_laps=53,
        track_status=TrackStatus.SAFETY_CAR,  # Active SC
    )
    drivers = {
        "VER": DriverState("VER", "Red Bull", 1, 0.0, 0.0, TyreCompound.MEDIUM, tyre_age=24),
        "HAM": DriverState("HAM", "Mercedes", 2, 3.5, 3.5, TyreCompound.MEDIUM, tyre_age=24),
    }
    state = RaceState(circuit, env, drivers)
    team = STRATOSStrategyTeam()
    synthesis = team.evaluate_turn(state, "VER")
    print_synthesis_result(synthesis)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="STRATOS Deliberative Multi-Agent Strategy Team")
    parser.add_argument(
        "--scenario",
        type=str,
        default="all",
        choices=["all", "undercut", "monaco_traffic", "rain", "safety_car"],
        help="Race scenario to simulate (default: all)",
    )
    args = parser.parse_args()

    dispatch = {
        "undercut": [run_undercut_scenario],
        "monaco_traffic": [run_monaco_traffic_scenario],
        "rain": [run_rain_scenario],
        "safety_car": [run_safety_car_scenario],
        "all": [
            run_undercut_scenario,
            run_monaco_traffic_scenario,
            run_rain_scenario,
            run_safety_car_scenario,
        ],
    }

    for fn in dispatch[args.scenario]:
        fn()


if __name__ == "__main__":
    main()
