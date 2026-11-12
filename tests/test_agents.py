"""Unit tests for STRATOS deliberative multi-agent architecture.

Tests the WeatherAgent, CompetitorAgent, RiskAgent, StrategicSynthesisAgent,
and STRATOSStrategyTeam coordinator across dry, wet, undercut, and caution scenarios.
"""

from __future__ import annotations

import pytest

from stratos.agents.base import (
    AgentReport,
    AgentUrgency,
    StrategicAction,
)
from stratos.agents.competitor import CompetitorAgent
from stratos.agents.risk import RiskAgent
from stratos.agents.team import STRATOSStrategyTeam
from stratos.agents.weather import WeatherAgent
from stratos.models.pit import TrackStatus
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    PitStopRecord,
    RaceState,
)
from stratos.models.tyre import TyreCompound


def test_agent_report_validation() -> None:
    """Verify confidence and risk score validation on AgentReport."""
    # Valid report
    rep = AgentReport(
        agent_name="TestAgent",
        recommendation=StrategicAction.STAY_OUT,
        confidence=0.8,
        risk_score=0.2,
    )
    assert rep.confidence == 0.8
    assert rep.risk_score == 0.2

    with pytest.raises(ValueError, match="confidence must be within"):
        AgentReport(
            agent_name="TestAgent",
            recommendation=StrategicAction.STAY_OUT,
            confidence=1.5,
        )

    with pytest.raises(ValueError, match="risk_score must be within"):
        AgentReport(
            agent_name="TestAgent",
            recommendation=StrategicAction.STAY_OUT,
            risk_score=-0.1,
        )


def _create_mock_race_state(
    circuit_name: str = "Silverstone",
    lap: int = 20,
    total_laps: int = 52,
    track_status: TrackStatus = TrackStatus.GREEN,
    rainfall: float = 0.0,
    track_temp: float = 35.0,
    overtaking_diff: float = 0.45,
) -> RaceState:
    """Helper to create a parameterized RaceState for agent testing."""
    circuit = CircuitConfig(
        name=circuit_name,
        total_laps=total_laps,
        base_lap_time=88.0,
        pit_transit_loss_green=25.0,
        overtaking_difficulty=overtaking_diff,
    )
    env = EnvironmentState(
        lap=lap,
        total_laps=total_laps,
        track_status=track_status,
        track_temp=track_temp,
        rainfall_intensity=rainfall,
    )
    drivers = {
        "VER": DriverState(
            driver_id="VER",
            team="Red Bull",
            position=1,
            gap_to_leader=0.0,
            interval_to_ahead=0.0,
            current_compound=TyreCompound.MEDIUM,
            tyre_age=lap,
        ),
        "NOR": DriverState(
            driver_id="NOR",
            team="McLaren",
            position=2,
            gap_to_leader=1.8,
            interval_to_ahead=1.8,
            current_compound=TyreCompound.MEDIUM,
            tyre_age=lap,
        ),
        "LEC": DriverState(
            driver_id="LEC",
            team="Ferrari",
            position=3,
            gap_to_leader=12.0,
            interval_to_ahead=10.2,
            current_compound=TyreCompound.HARD,
            tyre_age=lap,
        ),
    }
    return RaceState(circuit=circuit, environment=env, drivers=drivers)


# ==============================================================================
# WEATHER AGENT TESTS
# ==============================================================================


def test_weather_agent_dry_conditions() -> None:
    """Verify WeatherAgent response under dry stable conditions."""
    state = _create_mock_race_state(rainfall=0.0)
    agent = WeatherAgent()
    report = agent.evaluate(state, "VER")

    assert report.recommendation == StrategicAction.STAY_OUT
    assert report.urgency == AgentUrgency.LOW
    assert report.confidence > 0.90
    assert report.risk_score < 0.10


def test_weather_agent_crossover_to_intermediate() -> None:
    """Verify WeatherAgent flags critical intermediate crossover when rain hits."""
    # Rain at 0.8 mm/h exceeds intermediate threshold (0.3 mm/h)
    state = _create_mock_race_state(rainfall=0.8)
    agent = WeatherAgent()
    report = agent.evaluate(state, "VER")  # VER is on Medium slicks

    assert report.recommendation == StrategicAction.SWITCH_TO_INTERMEDIATE
    assert report.suggested_compound == TyreCompound.INTERMEDIATE
    assert report.urgency == AgentUrgency.CRITICAL
    assert report.risk_score >= 0.80


def test_weather_agent_torrential_rain() -> None:
    """Verify WeatherAgent mandates Full Wets when rain exceeds 2.0 mm/h."""
    state = _create_mock_race_state(rainfall=3.5)
    agent = WeatherAgent()
    report = agent.evaluate(state, "VER")

    assert report.recommendation == StrategicAction.SWITCH_TO_WET
    assert report.suggested_compound == TyreCompound.WET
    assert report.urgency == AgentUrgency.CRITICAL


def test_weather_agent_imminent_rain_forecast() -> None:
    """Verify WeatherAgent advises extending stint when rain arrives in 1-2 laps."""
    state = _create_mock_race_state(rainfall=0.0)  # currently dry
    agent = WeatherAgent()
    agent.set_forecast([0.1, 0.9, 1.5])  # rain hits on lap+2
    report = agent.evaluate(state, "VER")

    assert report.recommendation == StrategicAction.EXTEND_STINT
    assert report.urgency == AgentUrgency.HIGH
    assert "Rain detected on radar" in report.rationale


# ==============================================================================
# COMPETITOR AGENT TESTS
# ==============================================================================


def test_competitor_agent_undercut_attack() -> None:
    """Verify CompetitorAgent recognizes undercut attack opportunity for trailing car."""
    state = _create_mock_race_state(lap=18)
    agent = CompetitorAgent(undercut_threshold_seconds=2.5)

    # NOR is in P2, 1.8s behind VER -> inside undercut window
    report = agent.evaluate(state, "NOR")

    assert report.recommendation == StrategicAction.TRIGGER_UNDERCUT
    assert report.urgency == AgentUrgency.HIGH
    assert report.metrics["target_rival"] == "VER"
    assert report.suggested_compound == TyreCompound.HARD


def test_competitor_agent_defensive_cover() -> None:
    """Verify CompetitorAgent warns leader to cover trailing rival within undercut window."""
    state = _create_mock_race_state(lap=18)
    agent = CompetitorAgent(undercut_threshold_seconds=2.5)

    # VER is in P1, NOR is 1.8s behind
    report = agent.evaluate(state, "VER")

    assert report.recommendation == StrategicAction.COVER_COMPETITOR
    assert report.urgency == AgentUrgency.HIGH
    assert report.metrics["threat_rival"] == "NOR"


def test_competitor_agent_overcut_clean_air() -> None:
    """Verify CompetitorAgent recommends pushing in clean air when rival ahead pits."""
    state = _create_mock_race_state(lap=20)
    # Simulate VER having just pitted into pit lane
    ver = state.get_driver("VER")
    ver.is_in_pit = True
    ver.pit_stops.append(
        PitStopRecord(
            lap=20,
            compound_in=TyreCompound.MEDIUM,
            compound_out=TyreCompound.HARD,
            stationary_duration=2.4,
            total_loss=25.0,
        )
    )

    agent = CompetitorAgent()
    report = agent.evaluate(state, "NOR")

    assert report.recommendation == StrategicAction.PUSH_IN_CLEAN_AIR
    assert "Hammer Time" in report.rationale


# ==============================================================================
# RISK AGENT TESTS
# ==============================================================================


def test_risk_agent_active_safety_car() -> None:
    """Verify RiskAgent capitalizes on active Safety Car cheap pit window."""
    state = _create_mock_race_state(track_status=TrackStatus.SAFETY_CAR)
    agent = RiskAgent()
    report = agent.evaluate(state, "VER")

    assert report.recommendation == StrategicAction.BOX_THIS_LAP
    assert report.urgency == AgentUrgency.CRITICAL
    assert report.metrics["risk_category"] == "OPPORTUNITY_CHEAP_PIT"


def test_risk_agent_tyre_cliff_exceeded() -> None:
    """Verify RiskAgent triggers mandatory pit call when tyre cliff is exceeded."""
    state = _create_mock_race_state(lap=35)
    # VER tyre age 35 on Mediums (cliff is 28 laps)
    ver = state.get_driver("VER")
    ver.tyre_age = 35

    agent = RiskAgent()
    report = agent.evaluate(state, "VER")

    assert report.recommendation == StrategicAction.BOX_THIS_LAP
    assert report.urgency == AgentUrgency.CRITICAL
    assert report.metrics["is_cliff_exceeded"] is True
    assert report.risk_score >= 0.85


def test_risk_agent_monaco_traffic_warning() -> None:
    """Verify RiskAgent warns against pitting into dirty air at Monaco."""
    state = _create_mock_race_state(
        circuit_name="Monaco",
        lap=22,
        overtaking_diff=0.95,
    )
    # Add a slow backmarker right where the leader would emerge (0.7s ahead)
    # Pitting adds ~27.4s -> BOT at 26.7s means leader emerges 0.7s behind in dirty air
    state.drivers["BOT"] = DriverState(
        driver_id="BOT",
        team="Sauber",
        position=15,
        gap_to_leader=26.7,
        interval_to_ahead=1.0,
        current_compound=TyreCompound.HARD,
        tyre_age=22,
    )

    agent = RiskAgent()
    report = agent.evaluate(state, "VER")

    assert report.recommendation == StrategicAction.EXTEND_STINT
    assert report.metrics["in_traffic_post_pit"] is True
    assert "TRAFFIC WARNING" in report.rationale


# ==============================================================================
# STRATEGIC SYNTHESIZER & TEAM TESTS
# ==============================================================================


def test_synthesizer_weather_override() -> None:
    """Verify that WeatherAgent wet crossover overrides competitor dry tactics."""
    state = _create_mock_race_state(rainfall=1.5)  # Heavy rain
    team = STRATOSStrategyTeam()
    synthesis = team.evaluate_turn(state, "VER")

    # Even if competitor wants to stay out or cover, weather forces Inters
    assert synthesis.primary_action == StrategicAction.SWITCH_TO_INTERMEDIATE
    assert synthesis.chosen_compound == TyreCompound.INTERMEDIATE
    assert synthesis.urgency == AgentUrgency.CRITICAL


def test_synthesizer_monaco_traffic_arbitration() -> None:
    """Verify Synthesizer aborts competitor undercut if risk flags Monaco traffic."""
    state = _create_mock_race_state(
        circuit_name="Monaco",
        lap=20,
        overtaking_diff=0.95,
    )
    # Place a backmarker in NOR's pit window (NOR gap 1.8 + pit 27.4 = 29.2s; ZHO at 28.5s)
    state.drivers["ZHO"] = DriverState(
        driver_id="ZHO",
        team="Sauber",
        position=16,
        gap_to_leader=28.5,
        interval_to_ahead=1.0,
        current_compound=TyreCompound.HARD,
        tyre_age=20,
    )

    team = STRATOSStrategyTeam()
    synthesis = team.evaluate_turn(state, "NOR")

    # Competitor wanted undercut, but traffic at Monaco aborts it!
    assert synthesis.primary_action == StrategicAction.EXTEND_STINT
    assert "ABORT PIT CALL" in synthesis.executive_summary


def test_strategy_team_decision_logging() -> None:
    """Verify STRATOSStrategyTeam logs historical decision traces."""
    state = _create_mock_race_state(lap=15)
    team = STRATOSStrategyTeam()

    s1 = team.evaluate_turn(state, "VER")
    assert len(team.decision_history) == 1
    assert team.decision_history[0]["lap"] == 15
    assert team.decision_history[0]["target_driver"] == "VER"
    assert s1.confidence > 0.0
