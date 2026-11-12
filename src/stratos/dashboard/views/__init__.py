"""Dashboard tab views package."""

from __future__ import annotations

from stratos.dashboard.views.historical_stats import render_historical_stats_view
from stratos.dashboard.views.history_data import render_history_data_view
from stratos.dashboard.views.next_race import render_next_race_view
from stratos.dashboard.views.overview import render_overview_view
from stratos.dashboard.views.pit_simulator import render_pit_simulator_view
from stratos.dashboard.views.pit_wall import render_pit_wall_view
from stratos.dashboard.views.strategy_optimizer import render_strategy_optimizer_view
from stratos.dashboard.views.team_analysis import render_team_analysis_view
from stratos.dashboard.views.tyre_sandbox import render_tyre_sandbox_view

__all__ = [
    "render_historical_stats_view",
    "render_history_data_view",
    "render_next_race_view",
    "render_overview_view",
    "render_pit_simulator_view",
    "render_pit_wall_view",
    "render_strategy_optimizer_view",
    "render_team_analysis_view",
    "render_tyre_sandbox_view",
]
