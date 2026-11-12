"""Risk assessment and probabilistic uncertainty agent for STRATOS.

Evaluates Safety Car hazard rates, pit re-entry traffic exposure (dirty air
and DRS trains), tyre cliff wear escalation, and pit box execution variance.
"""

from __future__ import annotations

import logging
from typing import Any

from stratos.agents.base import AgentReport, AgentUrgency, BaseAgent, StrategicAction
from stratos.models.pit import PitLossModel, TrackStatus
from stratos.models.state import RaceState
from stratos.models.tyre import TyreCompound, TyreDegradationModel

logger = logging.getLogger(__name__)


# Historical safety car intervention probability by circuit
CIRCUIT_SC_PROBABILITIES: dict[str, float] = {
    "monaco": 0.75,
    "singapore": 0.85,
    "baku": 0.70,
    "jeddah": 0.70,
    "silverstone": 0.45,
    "spa": 0.50,
    "monza": 0.25,
    "red_bull_ring": 0.30,
    "default": 0.40,
}


class RiskAgent(BaseAgent):
    """Deliberative agent quantifying operational, kinematic, and probabilistic risks."""

    def __init__(
        self,
        name: str = "RiskAgent",
        tyre_model: TyreDegradationModel | None = None,
        pit_loss_model: PitLossModel | None = None,
    ) -> None:
        """Initialize the Risk Agent.

        Parameters
        ----------
        name : str
            Agent identifier.
        tyre_model : TyreDegradationModel or None
            Tyre model for evaluating cliff thresholds.
        pit_loss_model : PitLossModel or None
            Pit loss model for window projection.
        """
        super().__init__(name=name)
        self.tyre_model = tyre_model if tyre_model is not None else TyreDegradationModel()
        self.pit_loss_model = pit_loss_model

    def get_circuit_sc_hazard(self, circuit_name: str) -> float:
        """Retrieve baseline safety car hazard probability for circuit.

        Parameters
        ----------
        circuit_name : str
            Circuit name.

        Returns
        -------
        float
            Safety car probability between 0.0 and 1.0.
        """
        key = circuit_name.lower().replace(" ", "_")
        return CIRCUIT_SC_PROBABILITIES.get(key, CIRCUIT_SC_PROBABILITIES["default"])

    def evaluate(self, race_state: RaceState, target_driver_id: str) -> AgentReport:
        """Evaluate operational, traffic, and tyre degradation risks.

        Parameters
        ----------
        race_state : RaceState
            Current state of the race.
        target_driver_id : str
            Driver code being evaluated.

        Returns
        -------
        AgentReport
            Risk quantification report.
        """
        circuit = race_state.circuit
        env = race_state.environment
        driver = race_state.get_driver(target_driver_id)

        # 1. Evaluate Traffic Re-entry
        window_proj = race_state.predict_pit_rejoin(
            driver_id=target_driver_id,
            pit_loss_model=self.pit_loss_model,
        )

        in_traffic = window_proj["in_traffic"]
        projected_position = window_proj["projected_position"]
        car_ahead_post_pit = window_proj["car_ahead"]
        gap_ahead_post_pit = window_proj["gap_to_car_ahead"]

        # 2. Evaluate Tyre Cliff Hazard
        is_cliff_exceeded = self.tyre_model.is_cliff_exceeded(
            driver.current_compound,
            driver.tyre_age,
        )
        params = self.tyre_model.get_parameters(driver.current_compound)
        cliff_proximity = max(0.0, driver.tyre_age / params.cliff_threshold)

        # 3. Safety Car State & Hazard
        is_sc_active = env.track_status in (TrackStatus.SAFETY_CAR, TrackStatus.VSC)
        circuit_sc_prob = self.get_circuit_sc_hazard(circuit.name)

        metrics: dict[str, Any] = {
            "in_traffic_post_pit": in_traffic,
            "projected_rejoin_position": projected_position,
            "gap_ahead_post_pit": gap_ahead_post_pit,
            "car_ahead_post_pit": car_ahead_post_pit,
            "is_cliff_exceeded": is_cliff_exceeded,
            "cliff_proximity_ratio": round(cliff_proximity, 2),
            "circuit_sc_probability": circuit_sc_prob,
            "is_sc_or_vsc_active": is_sc_active,
        }

        # SCENARIO A: Safety Car or VSC is active RIGHT NOW (Golden Window)
        if is_sc_active:
            # Under SC or VSC, pitting saves ~10-14 seconds over racing speed!
            metrics["risk_category"] = "OPPORTUNITY_CHEAP_PIT"
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.BOX_THIS_LAP,
                suggested_compound=TyreCompound.HARD,
                urgency=AgentUrgency.CRITICAL,
                confidence=0.96,
                risk_score=0.10,  # Minimum risk because field is throttled
                metrics=metrics,
                rationale=(
                    f"GOLDEN WINDOW: Track status is {env.track_status.value}. "
                    "Pitting under caution saves 10-14s relative to Green Flag pit loss. "
                    "Risk of staying out on worn tyres while rivals take cheap stops is severe. "
                    "Box immediately to capitalize on reduced pit loss."
                ),
            )

        # SCENARIO B: Severe Tyre Cliff Exceeded (Catastrophic wear risk)
        if is_cliff_exceeded:
            metrics["risk_category"] = "TYRE_CLIFF_FAILURE"
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.BOX_THIS_LAP,
                suggested_compound=TyreCompound.HARD,
                urgency=AgentUrgency.CRITICAL,
                confidence=0.92,
                risk_score=0.88,
                metrics=metrics,
                rationale=(
                    f"HIGH RISK: Current {driver.current_compound.value} tyres are at "
                    f"lap {driver.tyre_age}, exceeding the degradation cliff threshold "
                    f"({params.cliff_threshold} laps). Continuing risks catastrophic loss of grip, "
                    "sub-optimal delta times, and puncture hazard. Box this lap."
                ),
            )

        # SCENARIO C: Severe Traffic Re-entry Hazard (e.g. Monaco, Singapore)
        if in_traffic and circuit.overtaking_difficulty >= 0.70:
            diff_score = circuit.overtaking_difficulty
            metrics["risk_category"] = "TRAFFIC_DRS_TRAIN"
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.EXTEND_STINT,
                suggested_compound=None,
                urgency=AgentUrgency.HIGH,
                confidence=0.86,
                risk_score=0.72,
                metrics=metrics,
                rationale=(
                    f"TRAFFIC WARNING: Pitting drops driver to P{projected_position}, "
                    f"emerging {gap_ahead_post_pit:.2f}s behind {car_ahead_post_pit}. "
                    f"At {circuit.name} (overtake difficulty {diff_score:.2f}), "
                    "passing is near impossible. Extend stint until a clear window opens."
                ),
            )

        # SCENARIO D: Approaching Cliff, Clean Re-entry Window Open
        if cliff_proximity >= 0.80 and not in_traffic:
            metrics["risk_category"] = "CONTROLLED_WINDOW"
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.BOX_NEXT_LAP,
                suggested_compound=TyreCompound.HARD,
                urgency=AgentUrgency.MEDIUM,
                confidence=0.84,
                risk_score=0.25,
                metrics=metrics,
                rationale=(
                    f"Controlled risk: Tyres at {driver.tyre_age} laps (80% of cliff life). "
                    f"Clean pit window is currently open (re-entry P{projected_position} with "
                    f"{gap_ahead_post_pit:.1f}s margin ahead). Prepare to pit within 1-2 laps."
                ),
            )

        # Baseline: Moderate/Low Risk
        composite_risk = 0.20 * cliff_proximity + 0.15 * (1.0 if in_traffic else 0.0)
        wear_pct = cliff_proximity * 100
        return AgentReport(
            agent_name=self.name,
            recommendation=StrategicAction.STAY_OUT,
            suggested_compound=None,
            urgency=AgentUrgency.LOW,
            confidence=0.85,
            risk_score=min(1.0, float(composite_risk)),
            metrics=metrics,
            rationale=(
                f"Operational risk is nominal (Tyre wear: {wear_pct:.0f}% of cliff). "
                "No critical safety car, traffic, or tyre hazards detected. Continue stint."
            ),
        )
