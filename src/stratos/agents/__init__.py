"""Deliberative multi-agent architecture for motorsport race strategy.

STRATOS employs specialized agents (Weather, Competitor, Risk, and Strategic Synthesis)
collaborating to formulate Pareto-optimal, explainable decisions under uncertainty.
"""

from __future__ import annotations

from stratos.agents.base import (
    AgentReport,
    AgentUrgency,
    BaseAgent,
    StrategicAction,
)
from stratos.agents.competitor import CompetitorAgent
from stratos.agents.risk import CIRCUIT_SC_PROBABILITIES, RiskAgent
from stratos.agents.synthesizer import StrategicSynthesis, StrategicSynthesisAgent
from stratos.agents.team import STRATOSStrategyTeam
from stratos.agents.weather import WeatherAgent

__all__ = [
    # Base
    "StrategicAction",
    "AgentUrgency",
    "AgentReport",
    "BaseAgent",
    # Agents
    "WeatherAgent",
    "CompetitorAgent",
    "RiskAgent",
    "CIRCUIT_SC_PROBABILITIES",
    "StrategicSynthesis",
    "StrategicSynthesisAgent",
    "STRATOSStrategyTeam",
]
