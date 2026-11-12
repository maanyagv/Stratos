"""Weather reasoning agent for STRATOS.

Monitors meteorological dynamics, track surface temperatures, precipitation
trajectories, and compound crossover thresholds (Dry -> Intermediate -> Wet).
"""

from __future__ import annotations

import logging
from typing import Any

from stratos.agents.base import AgentReport, AgentUrgency, BaseAgent, StrategicAction
from stratos.models.state import RaceState
from stratos.models.tyre import TyreCompound

logger = logging.getLogger(__name__)


class WeatherAgent(BaseAgent):
    """Deliberative agent reasoning about weather transitions and tyre crossover points."""

    def __init__(
        self,
        name: str = "WeatherAgent",
        intermediate_rain_threshold: float = 0.3,
        wet_rain_threshold: float = 2.0,
        rain_forecast_window: list[float] | None = None,
    ) -> None:
        """Initialize the Weather Agent.

        Parameters
        ----------
        name : str
            Agent identifier.
        intermediate_rain_threshold : float
            Precipitation rate (mm/h) at which Intermediate tyres become faster
            than slicks (crossover point).
        wet_rain_threshold : float
            Precipitation rate (mm/h) at which Full Wet tyres are required.
        rain_forecast_window : list[float] or None
            Forecasted precipitation rates for subsequent laps [lap+1, lap+2, ...].
        """
        super().__init__(name=name)
        self.intermediate_threshold = intermediate_rain_threshold
        self.wet_threshold = wet_rain_threshold
        self.forecast_window = rain_forecast_window or []

    def set_forecast(self, forecast: list[float]) -> None:
        """Update rainfall forecast for upcoming laps.

        Parameters
        ----------
        forecast : list[float]
            List of forecasted rainfall rates in mm/h.
        """
        self.forecast_window = list(forecast)

    def evaluate(self, race_state: RaceState, target_driver_id: str) -> AgentReport:
        """Evaluate weather conditions and compound appropriateness.

        Parameters
        ----------
        race_state : RaceState
            Current race state.
        target_driver_id : str
            Target driver.

        Returns
        -------
        AgentReport
            Weather evaluation report.
        """
        env = race_state.environment
        driver = race_state.get_driver(target_driver_id)
        current_compound = driver.current_compound
        current_rain = env.rainfall_intensity
        track_temp = env.track_temp

        metrics: dict[str, Any] = {
            "current_rain_mmh": current_rain,
            "track_temp_celsius": track_temp,
            "intermediate_threshold": self.intermediate_threshold,
            "wet_threshold": self.wet_threshold,
            "forecast_next_laps": self.forecast_window[:3],
        }

        # Check imminent forecast (next 1-3 laps)
        imminent_rain = any(r >= self.intermediate_threshold for r in self.forecast_window[:2])
        heavy_rain_incoming = any(r >= self.wet_threshold for r in self.forecast_window[:3])

        # 1. Torrential rain conditions -> Full Wets
        if current_rain >= self.wet_threshold:
            if current_compound == TyreCompound.WET:
                return AgentReport(
                    agent_name=self.name,
                    recommendation=StrategicAction.STAY_OUT,
                    suggested_compound=TyreCompound.WET,
                    urgency=AgentUrgency.LOW,
                    confidence=0.95,
                    risk_score=0.15,
                    metrics=metrics,
                    rationale=(
                        f"Track is heavily wet ({current_rain:.1f} mm/h). "
                        "Driver is already on Full Wets. Continue circulating."
                    ),
                )
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.SWITCH_TO_WET,
                suggested_compound=TyreCompound.WET,
                urgency=AgentUrgency.CRITICAL,
                confidence=0.98,
                risk_score=0.90,
                metrics=metrics,
                rationale=(
                    f"CRITICAL: Rain intensity ({current_rain:.1f} mm/h) exceeds full wet "
                    f"threshold ({self.wet_threshold:.1f} mm/h). High risk of aquaplaning. "
                    "Box immediately for Wets."
                ),
            )

        # 2. Damp / Intermediate conditions
        if current_rain >= self.intermediate_threshold:
            if current_compound == TyreCompound.INTERMEDIATE:
                # Check if rain is increasing to heavy wet
                if heavy_rain_incoming:
                    return AgentReport(
                        agent_name=self.name,
                        recommendation=StrategicAction.BOX_NEXT_LAP,
                        suggested_compound=TyreCompound.WET,
                        urgency=AgentUrgency.HIGH,
                        confidence=0.85,
                        risk_score=0.60,
                        metrics=metrics,
                        rationale=(
                            f"Currently on Intermediates ({current_rain:.1f} mm/h), but forecast "
                            "indicates torrential rain incoming. Prepare to switch to Full Wets."
                        ),
                    )
                return AgentReport(
                    agent_name=self.name,
                    recommendation=StrategicAction.STAY_OUT,
                    suggested_compound=TyreCompound.INTERMEDIATE,
                    urgency=AgentUrgency.LOW,
                    confidence=0.90,
                    risk_score=0.10,
                    metrics=metrics,
                    rationale=(
                        f"Conditions optimal for Intermediates ({current_rain:.1f} mm/h). "
                        "Maintain current stint."
                    ),
                )

            # Driver is on slicks in intermediate rain
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.SWITCH_TO_INTERMEDIATE,
                suggested_compound=TyreCompound.INTERMEDIATE,
                urgency=AgentUrgency.CRITICAL,
                confidence=0.95,
                risk_score=0.85,
                metrics=metrics,
                rationale=(
                    f"Rain intensity ({current_rain:.1f} mm/h) has crossed intermediate "
                    f"crossover ({self.intermediate_threshold:.1f} mm/h). "
                    "Slicks will bleed 8-15s per lap. Box this lap for Intermediates."
                ),
            )

        # 3. Dry track but rain is forecast in next 1-2 laps
        if imminent_rain:
            # If driver was considering pitting for dry tyres, warn against it!
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.EXTEND_STINT,
                suggested_compound=TyreCompound.INTERMEDIATE,
                urgency=AgentUrgency.HIGH,
                confidence=0.80,
                risk_score=0.65,
                metrics=metrics,
                rationale=(
                    "Rain detected on radar arriving within 1-2 laps. Do NOT pit for dry tyres. "
                    "Extend current stint to pit directly onto Intermediates once crossover hits."
                ),
            )

        # 4. Completely Dry conditions
        # Check if driver is mistakenly on wet/intermediate tyres on a drying track
        if current_compound in (TyreCompound.INTERMEDIATE, TyreCompound.WET):
            return AgentReport(
                agent_name=self.name,
                recommendation=StrategicAction.BOX_THIS_LAP,
                suggested_compound=TyreCompound.MEDIUM,
                urgency=AgentUrgency.HIGH,
                confidence=0.92,
                risk_score=0.75,
                metrics=metrics,
                rationale=(
                    f"Track is dry ({current_rain:.1f} mm/h, {track_temp:.1f}°C). "
                    f"Current {current_compound.value} tyres will overheat and grain rapidly. "
                    "Box immediately to fit dry slicks (Mediums/Hards)."
                ),
            )

        # Normal dry running
        return AgentReport(
            agent_name=self.name,
            recommendation=StrategicAction.STAY_OUT,
            suggested_compound=None,
            urgency=AgentUrgency.LOW,
            confidence=0.95,
            risk_score=0.05,
            metrics=metrics,
            rationale=(
                f"Track surface dry ({current_rain:.1f} mm/h, {track_temp:.1f}°C). "
                "No rain forecasted in short-term horizon. Proceed with dry baseline strategy."
            ),
        )
