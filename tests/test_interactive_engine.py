"""Unit tests for interactive telemetry engineer engine and multi-agent discussions."""

from __future__ import annotations

from stratos.models.interactive_engine import (
    EngineerInputState,
    InteractiveEngineerEngine,
)
from stratos.models.pit import TrackStatus
from stratos.models.tyre import TyreCompound


def test_interactive_engine_default_evaluation() -> None:
    """Test engine evaluates default engineer telemetry state."""
    engine = InteractiveEngineerEngine()
    state = EngineerInputState()
    result = engine.evaluate_engineer_inputs(state)

    assert result.optimal_pit_lap > 0
    assert result.pit_window_range[0] <= result.pit_window_range[1]
    assert result.recommended_compound in [TyreCompound.HARD, TyreCompound.MEDIUM]
    assert 0 <= result.win_probability_pct <= 100
    assert 0 <= result.podium_probability_pct <= 100
    assert 0 <= result.strategy_confidence_pct <= 100
    assert len(result.strategy_alternatives) >= 2
    assert len(result.dialogue_thread) == 4
    assert len(result.radio_transmission) > 0


def test_interactive_engine_rain_scenario() -> None:
    """Test engineer injecting rain forecast triggers wet crossover dialogue."""
    engine = InteractiveEngineerEngine()
    rain_state = EngineerInputState(
        rainfall=2.5,
        rain_forecast_laps=3,
        current_lap=18,
    )
    result = engine.evaluate_engineer_inputs(rain_state)

    assert result.recommended_compound == TyreCompound.INTERMEDIATE
    assert "Plan C" in result.plan_name or "Inter" in result.plan_name

    weather_msg = next(m for m in result.dialogue_thread if m.agent_id == "WEATHER")
    assert "rain" in weather_msg.dialogue_text.lower() or "wet" in weather_msg.dialogue_text.lower()
    assert "INTER" in weather_msg.directive_callout


def test_interactive_engine_safety_car_scenario() -> None:
    """Test engineer setting track status to Safety Car triggers cheap pit stop call."""
    engine = InteractiveEngineerEngine()
    sc_state = EngineerInputState(
        track_status=TrackStatus.SAFETY_CAR,
        current_lap=21,
        tyre_age=21,
    )
    result = engine.evaluate_engineer_inputs(sc_state)

    risk_msg = next(m for m in result.dialogue_thread if m.agent_id == "RISK")
    has_sc_text = (
        "safety car" in risk_msg.dialogue_text.lower()
        or "delta" in risk_msg.dialogue_text.lower()
    )
    assert has_sc_text

    chief_msg = next(m for m in result.dialogue_thread if m.agent_id == "CHIEF")
    assert "BOX" in chief_msg.directive_callout or "PIT" in chief_msg.directive_callout


def test_interactive_engine_rival_undercut_response() -> None:
    """Test rival pitting now triggers immediate defensive response."""
    engine = InteractiveEngineerEngine()
    rival_box_state = EngineerInputState(
        rival_action="boxed_now",
        rival_gap=1.2,
        current_lap=22,
    )
    result = engine.evaluate_engineer_inputs(rival_box_state)

    comp_msg = next(m for m in result.dialogue_thread if m.agent_id == "COMPETITOR")
    assert "boxed" in comp_msg.dialogue_text.lower() or "undercut" in comp_msg.dialogue_text.lower()
