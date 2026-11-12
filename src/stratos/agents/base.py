"""Base abstractions and communication protocols for STRATOS deliberative agents.

Every specialized agent observes the current race state, performs domain-specific
reasoning (weather, competitor tactics, probabilistic risk), and emits a typed
report with quantitative indicators, recommendations, confidence scores, and
human-interpretable rationale.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from stratos.models.state import RaceState
from stratos.models.tyre import TyreCompound

logger = logging.getLogger(__name__)


class StrategicAction(StrEnum):
    """Categorical strategic recommendations issued by agents."""

    STAY_OUT = "STAY_OUT"
    BOX_THIS_LAP = "BOX_THIS_LAP"
    BOX_NEXT_LAP = "BOX_NEXT_LAP"
    EXTEND_STINT = "EXTEND_STINT"
    TRIGGER_UNDERCUT = "TRIGGER_UNDERCUT"
    COVER_COMPETITOR = "COVER_COMPETITOR"
    SWITCH_TO_INTERMEDIATE = "SWITCH_TO_INTERMEDIATE"
    SWITCH_TO_WET = "SWITCH_TO_WET"
    CONSERVE_TYRES = "CONSERVE_TYRES"
    PUSH_IN_CLEAN_AIR = "PUSH_IN_CLEAN_AIR"


class AgentUrgency(StrEnum):
    """Urgency level associated with an agent's recommendation."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AgentReport:
    """Standardized deliberative report emitted by a specialist agent.

    Attributes
    ----------
    agent_name : str
        Identifier of the issuing agent (e.g., 'WeatherAgent', 'CompetitorAgent').
    recommendation : StrategicAction
        Categorical action suggested by this agent.
    suggested_compound : TyreCompound | None
        Target compound if a pit stop is recommended.
    urgency : AgentUrgency
        How time-critical this advice is.
    confidence : float
        Agent's confidence score between 0.0 (uncertain) and 1.0 (certain).
    risk_score : float
        Associated hazard / penalty score between 0.0 (no risk) and 1.0 (extreme risk).
    metrics : dict[str, Any]
        Key quantitative metrics supporting the reasoning.
    rationale : str
        Human-readable deliberative argument explaining the conclusion.
    """

    agent_name: str
    recommendation: StrategicAction
    suggested_compound: TyreCompound | None = None
    urgency: AgentUrgency = AgentUrgency.LOW
    confidence: float = 1.0
    risk_score: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def __post_init__(self) -> None:
        """Validate confidence and risk score ranges."""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be within [0.0, 1.0], got {self.confidence}")
        if not (0.0 <= self.risk_score <= 1.0):
            raise ValueError(f"risk_score must be within [0.0, 1.0], got {self.risk_score}")


class BaseAgent(ABC):
    """Abstract base class for all STRATOS deliberative agents."""

    def __init__(self, name: str) -> None:
        """Initialize the agent.

        Parameters
        ----------
        name : str
            Descriptive agent name.
        """
        self.name = name

    @abstractmethod
    def evaluate(self, race_state: RaceState, target_driver_id: str) -> AgentReport:
        """Evaluate race state and produce a specialized deliberative report.

        Parameters
        ----------
        race_state : RaceState
            Current comprehensive state of the race, circuit, and competitors.
        target_driver_id : str
            The driver identifier for whom strategy is being deliberated.

        Returns
        -------
        AgentReport
            Structured report with findings and recommendations.
        """
