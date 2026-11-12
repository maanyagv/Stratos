"""Tests for STRATOS dashboard styles, Plotly charts, and view modules."""

from __future__ import annotations

import plotly.graph_objects as go

from stratos.dashboard.charts import (
    plot_1stop_optimization_curve,
    plot_confidence_gauge,
    plot_degradation_predicted_vs_actual,
    plot_pit_window_rejoin,
    plot_sakhir_circuit_map,
    plot_strategy_comparison,
    plot_tyre_degradation_curves,
)
from stratos.dashboard.styles import get_css
from stratos.dashboard.views import (
    render_overview_view,
    render_pit_simulator_view,
    render_pit_wall_view,
    render_strategy_optimizer_view,
    render_tyre_sandbox_view,
)
from stratos.models.pit import PitLossModel, TrackStatus
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    RaceState,
)
from stratos.models.tyre import TyreCompound, TyreDegradationModel


def test_get_css_dark_and_light() -> None:
    """Verify CSS generation succeeds for both dark and light modes."""
    dark_css = get_css(is_dark=True)
    assert isinstance(dark_css, str)
    assert ".dashboard-card" in dark_css
    assert ".top-header" in dark_css
    assert ".sidebar-brand" in dark_css
    assert "#0b111e" in dark_css

    light_css = get_css(is_dark=False)
    assert isinstance(light_css, str)
    assert ".dashboard-card" in light_css
    assert "#f8fafc" in light_css


def test_plot_confidence_gauge() -> None:
    """Verify radial confidence gauge chart generates valid figure."""
    fig = plot_confidence_gauge(confidence_pct=78, is_dark=True)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert "78%" in fig.layout.annotations[0].text


def test_plot_sakhir_circuit_map() -> None:
    """Verify Sakhir circuit map generates valid figure with DRS zones and turns."""
    fig = plot_sakhir_circuit_map(is_dark=True)
    assert isinstance(fig, go.Figure)
    trace_names = [trace.name for trace in fig.data if trace.name]
    assert "Our car" in trace_names
    assert "Teammate" in trace_names
    assert "Rival" in trace_names
    # Check that annotations contain corner numbers
    ann_texts = [ann.text for ann in fig.layout.annotations]
    assert any("1" in str(t) for t in ann_texts)
    assert any("4" in str(t) for t in ann_texts)


def test_plot_degradation_predicted_vs_actual() -> None:
    """Verify Predicted vs Actual degradation chart generates curves and scatter dots."""
    fig = plot_degradation_predicted_vs_actual(is_dark=True)
    assert isinstance(fig, go.Figure)
    trace_names = [trace.name for trace in fig.data if trace.name]
    assert "Soft" in trace_names
    assert "Medium" in trace_names
    assert "Hard" in trace_names
    assert "Actual" in trace_names


def test_plot_tyre_degradation_curves() -> None:
    """Verify tyre wear Plotly curve generator produces valid figure."""
    model = TyreDegradationModel()
    fig = plot_tyre_degradation_curves(model, max_laps=35, track_temp=30.0, is_dark=True)

    assert isinstance(fig, go.Figure)
    trace_names = [trace.name for trace in fig.data]
    assert any("SOFT" in str(name) for name in trace_names)
    assert any("MEDIUM" in str(name) for name in trace_names)
    assert any("HARD" in str(name) for name in trace_names)


def test_plot_pit_window_rejoin() -> None:
    """Verify competitor re-entry timeline chart generation."""
    circuit = CircuitConfig(
        name="Silverstone",
        total_laps=52,
        base_lap_time=88.0,
        pit_transit_loss_green=25.6,
    )
    env = EnvironmentState(lap=20, total_laps=52, track_status=TrackStatus.GREEN)
    drivers = {
        "VER": DriverState("VER", "Red Bull", 1, 0.0, 0.0, TyreCompound.MEDIUM, tyre_age=20),
        "NOR": DriverState("NOR", "McLaren", 2, 2.0, 2.0, TyreCompound.MEDIUM, tyre_age=20),
        "LEC": DriverState("LEC", "Ferrari", 3, 27.0, 25.0, TyreCompound.HARD, tyre_age=20),
    }
    race_state = RaceState(circuit, env, drivers)
    pit_model = PitLossModel(circuit.to_pit_profile())

    fig = plot_pit_window_rejoin(
        race_state=race_state,
        target_driver_id="NOR",
        pit_loss_model=pit_model,
        is_dark=True,
    )

    assert isinstance(fig, go.Figure)
    trace_names = [trace.name for trace in fig.data]
    assert "VER" in trace_names
    assert "NOR" in trace_names
    assert "Projected Re-entry" in trace_names


def test_plot_pit_window_rejoin_traffic_highlight() -> None:
    """Verify dirty air wake is annotated when target pits within 1.5s of a car."""
    circuit = CircuitConfig("Monza", 53, 80.0, 22.0)
    env = EnvironmentState(lap=20, total_laps=53, track_status=TrackStatus.GREEN)
    drivers = {
        "VER": DriverState("VER", "Red Bull", 1, 0.0, 0.0, TyreCompound.MEDIUM, tyre_age=20),
        "NOR": DriverState("NOR", "McLaren", 2, 2.0, 2.0, TyreCompound.MEDIUM, tyre_age=20),
        "LEC": DriverState("LEC", "Ferrari", 3, 25.5, 23.5, TyreCompound.HARD, tyre_age=20),
    }
    race_state = RaceState(circuit, env, drivers)
    fig = plot_pit_window_rejoin(race_state, target_driver_id="NOR", is_dark=True)

    assert isinstance(fig, go.Figure)
    assert len(fig.layout.shapes) > 0


def test_plot_1stop_optimization_curve() -> None:
    """Verify 1-stop sweep optimization curve generator produces valid figure."""
    circuit = CircuitConfig("Silverstone", 52, 88.0, 25.6)
    fig = plot_1stop_optimization_curve(
        circuit=circuit,
        compound1=TyreCompound.MEDIUM,
        compound2=TyreCompound.HARD,
        track_temp=35.0,
        is_dark=True,
    )

    assert isinstance(fig, go.Figure)
    trace_names = [trace.name for trace in fig.data]
    assert "Race Time Penalty vs Optimal" in trace_names
    assert "Optimal Pit Lap" in trace_names


def test_plot_strategy_comparison() -> None:
    """Verify strategy candidate bar chart generator."""
    comparisons = [
        {
            "strategy_name": "Medium -> Hard",
            "total_time_seconds": 4720.5,
            "delta_to_fastest_seconds": 0.0,
        },
        {
            "strategy_name": "Soft -> Hard",
            "total_time_seconds": 4725.2,
            "delta_to_fastest_seconds": 4.7,
        },
    ]
    fig = plot_strategy_comparison(comparisons, is_dark=True)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert isinstance(fig.data[0], go.Bar)


def test_plot_multi_season_strategy_distribution() -> None:
    """Verify multi-season stacked bar chart generator."""
    from stratos.dashboard.charts import plot_multi_season_strategy_distribution
    from stratos.data.historical_db import get_multi_season_strategy_distribution

    dist = get_multi_season_strategy_distribution()
    fig = plot_multi_season_strategy_distribution(dist, is_dark=True)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3
    assert fig.layout.barmode == "stack"


def test_views_callability() -> None:
    """Verify all dashboard tab view functions exist and are callable."""
    from stratos.dashboard.views import render_historical_stats_view

    assert callable(render_overview_view)
    assert callable(render_historical_stats_view)
    assert callable(render_pit_wall_view)
    assert callable(render_tyre_sandbox_view)
    assert callable(render_pit_simulator_view)
    assert callable(render_strategy_optimizer_view)

