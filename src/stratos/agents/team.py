"""Multi-agent coordinator and strategic pit wall team for STRATOS.

Coordinates the WeatherAgent, CompetitorAgent, RiskAgent, and StrategicSynthesisAgent
to evaluate race states in real-time or offline benchmark runs.
"""

from __future__ import annotations

import logging
from typing import Any

from stratos.agents.competitor import CompetitorAgent
from stratos.agents.risk import RiskAgent
from stratos.agents.synthesizer import StrategicSynthesis, StrategicSynthesisAgent
from stratos.agents.weather import WeatherAgent
from stratos.models.state import RaceState

logger = logging.getLogger(__name__)


class STRATOSStrategyTeam:
    """Orchestrator managing multi-agent deliberation for race strategy decisions."""

    def __init__(
        self,
        weather_agent: WeatherAgent | None = None,
        competitor_agent: CompetitorAgent | None = None,
        risk_agent: RiskAgent | None = None,
        synthesizer: StrategicSynthesisAgent | None = None,
    ) -> None:
        """Initialize the STRATOS multi-agent strategy team.

        Parameters
        ----------
        weather_agent : WeatherAgent or None
            Meteorological specialist.
        competitor_agent : CompetitorAgent or None
            Competitor tactics specialist.
        risk_agent : RiskAgent or None
            Operational risk and safety car specialist.
        synthesizer : StrategicSynthesisAgent or None
            Consensus strategist.
        """
        self.weather_agent = weather_agent if weather_agent is not None else WeatherAgent()
        self.competitor_agent = (
            competitor_agent if competitor_agent is not None else CompetitorAgent()
        )
        self.risk_agent = risk_agent if risk_agent is not None else RiskAgent()
        self.synthesizer = synthesizer if synthesizer is not None else StrategicSynthesisAgent()

        self._decision_history: list[dict[str, Any]] = []

    @property
    def decision_history(self) -> list[dict[str, Any]]:
        """Log of all past strategic decisions evaluated by the team."""
        return self._decision_history

    def evaluate_turn(
        self,
        race_state: RaceState,
        target_driver_id: str,
    ) -> StrategicSynthesis:
        """Execute full multi-agent deliberation on the current race lap.

        Parameters
        ----------
        race_state : RaceState
            Current state of the race, circuit, and all drivers.
        target_driver_id : str
            Driver for whom strategy is evaluated.

        Returns
        -------
        StrategicSynthesis
            Comprehensive multi-agent consensus decision.
        """
        # 1. Specialists evaluate race state in parallel/sequence
        weather_report = self.weather_agent.evaluate(race_state, target_driver_id)
        competitor_report = self.competitor_agent.evaluate(race_state, target_driver_id)
        risk_report = self.risk_agent.evaluate(race_state, target_driver_id)

        # 2. Synthesis agent arbitrates trade-offs and issues directive
        synthesis = self.synthesizer.synthesize(
            race_state=race_state,
            target_driver_id=target_driver_id,
            weather_report=weather_report,
            competitor_report=competitor_report,
            risk_report=risk_report,
        )

        # 3. Log decision record
        record = {
            "lap": race_state.environment.lap,
            "target_driver": target_driver_id,
            "primary_action": synthesis.primary_action.value,
            "chosen_compound": (
                synthesis.chosen_compound.value if synthesis.chosen_compound else None
            ),
            "urgency": synthesis.urgency.value,
            "confidence": synthesis.confidence,
            "composite_risk": synthesis.composite_risk,
            "executive_summary": synthesis.executive_summary,
        }
        self._decision_history.append(record)

        return synthesis
