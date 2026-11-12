"""Competitor modeling and tactical rivalry agent for STRATOS.

Monitors rival pit stop windows, calculates undercut strike opportunities,
detects defensive undercut exposure from trailing competitors, and assesses
clean air overcut windows.
"""

from __future__ import annotations

import logging
from typing import Any

from stratos.agents.base import AgentReport, AgentUrgency, BaseAgent, StrategicAction
from stratos.models.pit import PitLossModel
from stratos.models.state import RaceState
from stratos.models.tyre import TyreCompound

logger = logging.getLogger(__name__)


class CompetitorAgent(BaseAgent):
    """Deliberative agent analyzing competitor tactics, undercuts, and track position."""

    def __init__(
        self,
        name: str = "CompetitorAgent",
        undercut_threshold_seconds: float = 2.5,
        pit_loss_model: PitLossModel | None = None,
    ) -> None:
        """Initialize the Competitor Agent.

        Parameters
        ----------
        name : str
            Agent identifier.
        undercut_threshold_seconds : float
            Maximum gap in seconds within which an undercut attack or defensive threat exists.
        pit_loss_model : PitLossModel or None
            Pit loss estimator.
        """
        super().__init__(name=name)
        self.undercut_threshold = undercut_threshold_seconds
        self.pit_loss_model = pit_loss_model

    def evaluate(self, race_state: RaceState, target_driver_id: str) -> AgentReport:
        """Evaluate competitor gaps and identify undercut / defensive opportunities.

        Parameters
        ----------
        race_state : RaceState
            Current state of the race.
        target_driver_id : str
            Target driver code (e.g., 'VER', 'NOR').

        Returns
        -------
        AgentReport
            Tactical competitor analysis report.
        """
        driver = race_state.get_driver(target_driver_id)
        standings = race_state.get_standings()
        active_standings = [d for d in standings if not d.is_retired]

        # Find target driver position index
        driver_idx = next(
            (i for i, d in enumerate(active_standings) if d.driver_id == target_driver_id),
            None,
        )
        if driver_idx is None:
            raise KeyError(f"Driver '{target_driver_id}' not found in active standings.")

        # Identify immediate competitors ahead and behind
        competitor_ahead = active_standings[driver_idx - 1] if driver_idx > 0 else None
        competitor_behind = (
            active_standings[driver_idx + 1] if driver_idx < len(active_standings) - 1 else None
        )

        metrics: dict[str, Any] = {
            "driver_position": driver.position,
            "driver_compound": driver.current_compound.value,
            "driver_tyre_age": driver.tyre_age,
            "car_ahead_id": competitor_ahead.driver_id if competitor_ahead else None,
            "interval_ahead": driver.interval_to_ahead if competitor_ahead else None,
            "car_behind_id": competitor_behind.driver_id if competitor_behind else None,
            "interval_behind": competitor_behind.interval_to_ahead if competitor_behind else None,
        }

        # Check if driver has already pitted vs competitors
        target_stops = len(driver.pit_stops)

        # 1. Undercut Attack Scenario: Chasing a car ahead within strike distance
        if (
            competitor_ahead is not None
            and driver.interval_to_ahead <= self.undercut_threshold
            and len(competitor_ahead.pit_stops) == target_stops  # on same stint
            and driver.tyre_age >= 12  # Tyres sufficiently worn for fresh set to offer pace delta
        ):
            metrics["tactic"] = "UNDERCUT_ATTACK"
            metrics["target_rival"] = competitor_ahead.driver_id
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.TRIGGER_UNDERCUT,
                suggested_compound=TyreCompound.HARD,
                urgency=AgentUrgency.HIGH,
                confidence=0.88,
                risk_score=0.35,
                metrics=metrics,
                rationale=(
                    f"Driver is within undercut strike distance of {competitor_ahead.driver_id} "
                    f"({driver.interval_to_ahead:.2f}s behind). Pitting now for fresh tyres "
                    "will create a 1.5-2.0s out-lap pace delta to jump ahead once rival pits."
                ),
            )

        # 2. Defensive Undercut Exposure: Defending against trailing car in strike distance
        if (
            competitor_behind is not None
            and competitor_behind.interval_to_ahead <= self.undercut_threshold
            and len(competitor_behind.pit_stops) == target_stops
            and driver.tyre_age >= 16  # In pit window
        ):
            metrics["tactic"] = "DEFENSIVE_COVER"
            metrics["threat_rival"] = competitor_behind.driver_id
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.COVER_COMPETITOR,
                suggested_compound=TyreCompound.HARD,
                urgency=AgentUrgency.HIGH,
                confidence=0.85,
                risk_score=0.45,
                metrics=metrics,
                rationale=(
                    f"VULNERABLE: {competitor_behind.driver_id} is trailing by only "
                    f"{competitor_behind.interval_to_ahead:.2f}s within the undercut window. "
                    "If they pit first, we lose track position. "
                    "Box this lap to cover the undercut threat."
                ),
            )

        # 3. Clean Air Overcut Opportunity: Competitor ahead just pitted into traffic
        if (
            competitor_ahead is not None
            and len(competitor_ahead.pit_stops) > target_stops  # car ahead has pitted
            and competitor_ahead.is_in_pit
        ):
            metrics["tactic"] = "OVERCUT_CLEAN_AIR"
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.PUSH_IN_CLEAN_AIR,
                suggested_compound=None,
                urgency=AgentUrgency.MEDIUM,
                confidence=0.82,
                risk_score=0.20,
                metrics=metrics,
                rationale=(
                    f"{competitor_ahead.driver_id} pitted into pit lane. We have clean air ahead. "
                    "Execute 'Hammer Time': push on warm tyres with low fuel to extend our lead "
                    "before executing our own pit stop."
                ),
            )

        # 4. Large Gap / Free Pit Window (buffer > 25s over car behind)
        if competitor_behind is not None and competitor_behind.interval_to_ahead >= 26.0:
            metrics["tactic"] = "FREE_PIT_STOP"
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.BOX_THIS_LAP,
                suggested_compound=TyreCompound.HARD,
                urgency=AgentUrgency.MEDIUM,
                confidence=0.90,
                risk_score=0.10,
                metrics=metrics,
                rationale=(
                    f"Driver holds a massive {competitor_behind.interval_to_ahead:.1f}s gap to "
                    f"{competitor_behind.driver_id}. A pit stop costs ~22-25s. "
                    "We have a 'free pit stop' window: pit now with guaranteed position retention."
                ),
            )

        # Default: Stable position, maintain current stint
        gap_behind_val = competitor_behind.interval_to_ahead if competitor_behind else 0.0
        return AgentReport(
            agent_name=self.name,
            recommendation=StrategicAction.STAY_OUT,
            suggested_compound=None,
            urgency=AgentUrgency.LOW,
            confidence=0.80,
            risk_score=0.15,
            metrics=metrics,
            rationale=(
                f"Track gaps are stable (Ahead: {driver.interval_to_ahead:.1f}s, "
                f"Behind: {gap_behind_val:.1f}s). "
                "No immediate undercut threat or strike window. Continue current stint."
            ),
        )
