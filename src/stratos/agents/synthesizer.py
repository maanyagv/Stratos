"""Strategic synthesis and deliberative consensus agent for STRATOS.

Integrates domain-specific findings from Weather, Competitor, and Risk agents,
resolves tactical trade-offs (e.g. undercut reward vs traffic re-entry penalty),
and issues Pareto-optimal race strategy decisions with race-engineer rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from stratos.agents.base import AgentReport, AgentUrgency, BaseAgent, StrategicAction
from stratos.models.state import RaceState
from stratos.models.tyre import TyreCompound

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategicSynthesis:
    """Consolidated race strategy decision issued by the STRATOS synthesis engine.

    Attributes
    ----------
    target_driver : str
        Driver code for whom the decision was formulated.
    primary_action : StrategicAction
        Final consensus strategic recommendation.
    chosen_compound : TyreCompound | None
        Tyre compound to fit if a pit stop is scheduled.
    urgency : AgentUrgency
        Execution urgency (LOW, MEDIUM, HIGH, CRITICAL).
    confidence : float
        Overall synthesis confidence score [0.0, 1.0].
    composite_risk : float
        Synthesized risk index [0.0, 1.0].
    alternative_action : StrategicAction | None
        Viable secondary tactical option if conditions change.
    executive_summary : str
        Concise, radio-call style strategic command.
    deliberative_rationale : str
        Comprehensive multi-agent synthesis explaining how trade-offs were resolved.
    agent_reports : dict[str, AgentReport]
        Underlying specialist reports that informed the decision.
    """

    target_driver: str
    primary_action: StrategicAction
    chosen_compound: TyreCompound | None
    urgency: AgentUrgency
    confidence: float
    composite_risk: float
    alternative_action: StrategicAction | None = None
    executive_summary: str = ""
    deliberative_rationale: str = ""
    agent_reports: dict[str, AgentReport] = field(default_factory=dict)


class StrategicSynthesisAgent(BaseAgent):
    """Lead race strategist resolving agent tensions and issuing optimal directives."""

    def __init__(self, name: str = "StrategicSynthesizer") -> None:
        """Initialize the strategic synthesis agent."""
        super().__init__(name=name)

    def evaluate(self, race_state: RaceState, target_driver_id: str) -> AgentReport:
        """Issue standalone agent report (satisfying BaseAgent interface)."""
        # Standalone evaluation defers to full synthesis
        driver = race_state.get_driver(target_driver_id)
        return AgentReport(
            agent_name=self.name,
            recommendation=StrategicAction.STAY_OUT,
            suggested_compound=driver.current_compound,
            urgency=AgentUrgency.LOW,
            confidence=0.85,
            risk_score=0.10,
            rationale="Strategic synthesis awaiting multi-agent inputs.",
        )

    def synthesize(
        self,
        race_state: RaceState,
        target_driver_id: str,
        weather_report: AgentReport,
        competitor_report: AgentReport,
        risk_report: AgentReport,
    ) -> StrategicSynthesis:
        """Synthesize specialist reports into an authoritative race strategy decision.

        Arbitrates priorities:
          1. Meteorological imperatives (wet/inters crossover) override dry tactics.
          2. Active Safety Car / VSC windows offer priority cheap pit opportunities.
          3. Severe tyre cliff wear demands immediate pit action to avoid puncture.
          4. Competitor undercuts/covers are balanced against traffic re-entry risk.

        Parameters
        ----------
        race_state : RaceState
            Current state of the race.
        target_driver_id : str
            Target driver.
        weather_report : AgentReport
            Report from WeatherAgent.
        competitor_report : AgentReport
            Report from CompetitorAgent.
        risk_report : AgentReport
            Report from RiskAgent.

        Returns
        -------
        StrategicSynthesis
            Authoritative, explainable race strategy directive.
        """
        driver = race_state.get_driver(target_driver_id)
        reports = {
            weather_report.agent_name: weather_report,
            competitor_report.agent_name: competitor_report,
            risk_report.agent_name: risk_report,
        }

        # PRIORITY 1: Meteorological Imperatives (Crossover / Imminent Rain)
        if weather_report.recommendation in (
            StrategicAction.SWITCH_TO_WET,
            StrategicAction.SWITCH_TO_INTERMEDIATE,
        ):
            wet_name = (
                weather_report.suggested_compound.value
                if weather_report.suggested_compound
                else "WET"
            )
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=weather_report.recommendation,
                chosen_compound=weather_report.suggested_compound,
                urgency=AgentUrgency.CRITICAL,
                confidence=weather_report.confidence,
                composite_risk=weather_report.risk_score,
                alternative_action=StrategicAction.STAY_OUT,
                executive_summary=(
                    f"BOX BOX BOX! Fit {wet_name} tyres! "
                    "Precipitation has crossed the wet crossover threshold."
                ),
                deliberative_rationale=(
                    f"Weather agent flagged critical condition: {weather_report.rationale} "
                    "Kinematic pace deficit on dry tyres in wet conditions exceeds 10s/lap, "
                    "superseding all competitor and traffic considerations."
                ),
                agent_reports=reports,
            )

        if weather_report.recommendation == StrategicAction.EXTEND_STINT:
            # Imminent rain forecast
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=StrategicAction.EXTEND_STINT,
                chosen_compound=None,
                urgency=AgentUrgency.HIGH,
                confidence=weather_report.confidence,
                composite_risk=0.35,
                alternative_action=competitor_report.recommendation,
                executive_summary=(
                    "STAY OUT! Rain is 1-2 laps away. Extend stint for direct wet tyre switch."
                ),
                deliberative_rationale=(
                    f"Weather synthesis: {weather_report.rationale} "
                    "Pitting now for dry tyres would result in an extra pit stop when rain hits. "
                    "Stint extended to minimize total race pit loss."
                ),
                agent_reports=reports,
            )

        # PRIORITY 2: Active Safety Car or VSC (Cheap Pit Stop Window)
        if risk_report.metrics.get("is_sc_or_vsc_active"):
            chosen = competitor_report.suggested_compound or TyreCompound.HARD
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=StrategicAction.BOX_THIS_LAP,
                chosen_compound=chosen,
                urgency=AgentUrgency.CRITICAL,
                confidence=0.96,
                composite_risk=0.10,
                alternative_action=StrategicAction.STAY_OUT,
                executive_summary=(
                    f"BOX THIS LAP! Pit under {race_state.environment.track_status.value}. "
                    f"Fit {chosen.value} tyres."
                ),
                deliberative_rationale=(
                    f"Risk synthesis: {risk_report.rationale} "
                    "Pitting under caution saves 10-14 seconds over green flag transit loss. "
                    "Guarantees significant net race time advantage."
                ),
                agent_reports=reports,
            )

        # PRIORITY 3: Tyre Cliff Hazard Exceeded
        if risk_report.metrics.get("is_cliff_exceeded"):
            chosen = competitor_report.suggested_compound or TyreCompound.HARD
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=StrategicAction.BOX_THIS_LAP,
                chosen_compound=chosen,
                urgency=AgentUrgency.CRITICAL,
                confidence=0.92,
                composite_risk=0.85,
                alternative_action=None,
                executive_summary=f"BOX THIS LAP! Tyres at cliff limit. Fit fresh {chosen.value}.",
                deliberative_rationale=(
                    f"Risk synthesis: {risk_report.rationale} "
                    "Degradation cliff reached; continuing will induce catastrophic pace loss "
                    "and puncture hazard."
                ),
                agent_reports=reports,
            )

        # PRIORITY 4: Tactical Competitor & Traffic Trade-off Arbitration
        # Competitor wants pit (Undercut or Cover), but Risk warns of heavy traffic
        wants_pit = competitor_report.recommendation in (
            StrategicAction.TRIGGER_UNDERCUT,
            StrategicAction.COVER_COMPETITOR,
            StrategicAction.BOX_THIS_LAP,
        )
        has_traffic_risk = risk_report.metrics.get("in_traffic_post_pit", False)
        overtaking_diff = race_state.circuit.overtaking_difficulty

        if wants_pit and has_traffic_risk and overtaking_diff >= 0.75:
            # At difficult circuits (Monaco, Singapore), traffic is fatal to an undercut!
            car_ahead = risk_report.metrics.get("car_ahead_post_pit")
            rejoin_pos = risk_report.metrics.get("projected_rejoin_position")
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=StrategicAction.EXTEND_STINT,
                chosen_compound=None,
                urgency=AgentUrgency.HIGH,
                confidence=0.84,
                composite_risk=0.60,
                alternative_action=competitor_report.recommendation,
                executive_summary=(
                    f"ABORT PIT CALL! Traffic alert: pitting drops to P{rejoin_pos} "
                    f"behind {car_ahead} in dirty air. Extend stint in clean air."
                ),
                deliberative_rationale=(
                    f"Arbitration: Competitor requested {competitor_report.recommendation.value}, "
                    f"but Risk Agent identified severe traffic at {race_state.circuit.name} "
                    f"({risk_report.rationale}). Because overtaking difficulty is "
                    f"{overtaking_diff:.2f}, tyre pace advantage would be lost behind traffic. "
                    "Stint is extended to seek a clear pit window."
                ),
                agent_reports=reports,
            )

        # Approved Competitor Tactic (Undercut or Cover with acceptable traffic window)
        if competitor_report.recommendation == StrategicAction.TRIGGER_UNDERCUT:
            chosen = competitor_report.suggested_compound or TyreCompound.HARD
            rejoin_pos = risk_report.metrics.get("projected_rejoin_position")
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=StrategicAction.TRIGGER_UNDERCUT,
                chosen_compound=chosen,
                urgency=AgentUrgency.HIGH,
                confidence=competitor_report.confidence,
                composite_risk=risk_report.risk_score,
                alternative_action=StrategicAction.STAY_OUT,
                executive_summary=(
                    f"BOX BOX BOX! Trigger undercut! Fit {chosen.value}. "
                    "Push hard on the out-lap to jump rival!"
                ),
                deliberative_rationale=(
                    f"Competitor synthesis: {competitor_report.rationale} "
                    f"Risk clearance confirmed (Rejoin P{rejoin_pos}). "
                    "Executing early pit stop to exploit fresh tyre pace differential."
                ),
                agent_reports=reports,
            )

        if competitor_report.recommendation == StrategicAction.COVER_COMPETITOR:
            chosen = competitor_report.suggested_compound or TyreCompound.HARD
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=StrategicAction.COVER_COMPETITOR,
                chosen_compound=chosen,
                urgency=AgentUrgency.HIGH,
                confidence=competitor_report.confidence,
                composite_risk=risk_report.risk_score,
                alternative_action=StrategicAction.STAY_OUT,
                executive_summary=(f"BOX BOX BOX! Cover trailing rival! Fit {chosen.value}."),
                deliberative_rationale=(
                    f"Competitor synthesis: {competitor_report.rationale} "
                    "Defending track position against trailing competitor undercut attempt. "
                    "Immediate pit stop neutralizes rival strike window."
                ),
                agent_reports=reports,
            )

        if competitor_report.recommendation == StrategicAction.PUSH_IN_CLEAN_AIR:
            return StrategicSynthesis(
                target_driver=target_driver_id,
                primary_action=StrategicAction.PUSH_IN_CLEAN_AIR,
                chosen_compound=None,
                urgency=AgentUrgency.MEDIUM,
                confidence=0.85,
                composite_risk=0.15,
                alternative_action=StrategicAction.BOX_NEXT_LAP,
                executive_summary=(
                    "HAMMER TIME! Clean air ahead. Push maximum pace on current tyres."
                ),
                deliberative_rationale=(
                    f"Competitor synthesis: {competitor_report.rationale} "
                    "Car ahead pitted into traffic. Driver possesses clean air; optimal strategy "
                    "is to burn low fuel on warm tyres to extend net advantage."
                ),
                agent_reports=reports,
            )

        # DEFAULT: Maintain Stint
        composite = (
            weather_report.risk_score + competitor_report.risk_score + risk_report.risk_score
        ) / 3.0
        return StrategicSynthesis(
            target_driver=target_driver_id,
            primary_action=StrategicAction.STAY_OUT,
            chosen_compound=driver.current_compound,
            urgency=AgentUrgency.LOW,
            confidence=0.88,
            composite_risk=float(composite),
            alternative_action=StrategicAction.CONSERVE_TYRES,
            executive_summary="STAY OUT. Strategy is green. Maintain target lap times.",
            deliberative_rationale=(
                "All specialist agents report stable race parameters. "
                f"Weather is dry, track gaps are stable ({competitor_report.rationale}), "
                f"and operational risk is nominal ({risk_report.rationale}). "
                "Proceed with planned stint."
            ),
            agent_reports=reports,
        )
