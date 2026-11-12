"""Plotly chart generators for STRATOS race strategy visualization.

Includes interactive compound wear curves, horizontal pit window re-entry timelines,
1-stop optimization curves, multi-strategy benchmarking charts, Sakhir circuit map,
radial confidence gauges, and predicted vs actual degradation plots.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go

from stratos.models.pit import PitLossModel
from stratos.models.state import CircuitConfig, RaceState
from stratos.models.strategy import StintPlan, StrategyEvaluator, StrategyPlan
from stratos.models.tyre import TyreCompound, TyreDegradationModel

COMPOUND_COLORS: dict[TyreCompound, str] = {
    TyreCompound.SOFT: "#ef4444",
    TyreCompound.MEDIUM: "#eab308",
    TyreCompound.HARD: "#f8fafc",
    TyreCompound.INTERMEDIATE: "#22c55e",
    TyreCompound.WET: "#3b82f6",
}


def get_base_layout(is_dark: bool = True) -> dict[str, Any]:
    """Return common Plotly layout with dark/light theme parameters."""
    font_color = "#94a3b8" if is_dark else "#64748b"
    grid_color = "rgba(255,255,255,0.06)" if is_dark else "rgba(0,0,0,0.06)"

    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color=font_color, size=11),
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis=dict(
            gridcolor=grid_color,
            zerolinecolor=grid_color,
            tickfont=dict(size=10, color=font_color),
        ),
        yaxis=dict(
            gridcolor=grid_color,
            zerolinecolor=grid_color,
            tickfont=dict(size=10, color=font_color),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10, color=font_color),
        ),
    )


def plot_tyre_degradation_curves(
    tyre_model: TyreDegradationModel,
    max_laps: int = 50,
    track_temp: float = 35.0,
    is_dark: bool = True,
) -> go.Figure:
    """Plot interactive tyre degradation penalties across compounds vs tyre age."""
    fig = go.Figure()
    laps = list(range(max_laps + 1))

    for comp in [TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD]:
        color = COMPOUND_COLORS[comp]
        penalties = [tyre_model.lap_time_penalty(comp, age, track_temp=track_temp) for age in laps]
        params = tyre_model.get_parameters(comp)

        hover = (
            f"<b>{comp.value}</b><br>Age: %{{x}} laps<br>Penalty: +%{{{{y:.2f}}}}s<extra></extra>"
        )

        fig.add_trace(
            go.Scatter(
                x=laps,
                y=penalties,
                mode="lines",
                name=f"{comp.value} (Cliff: L{params.cliff_threshold})",
                line=dict(color=color, width=2.5),
                hovertemplate=hover,
            )
        )

        fig.add_vline(
            x=params.cliff_threshold,
            line=dict(color=color, width=1, dash="dot"),
            annotation_text=f"{comp.value[0]} Cliff",
            annotation_position="top left",
            annotation_font=dict(size=9, color=color),
        )

    layout = get_base_layout(is_dark)
    layout.update(
        title=dict(text="Compound Pace & Degradation Progression (+s/lap)", font=dict(size=13)),
        xaxis_title="Tyre Age (Completed Laps)",
        yaxis_title="Pace Delta vs Lap 0 Soft (s)",
    )
    fig.update_layout(**layout)
    return fig


def plot_pit_window_rejoin(
    race_state: RaceState,
    target_driver_id: str,
    pit_loss_model: PitLossModel | None = None,
    is_dark: bool = True,
) -> go.Figure:
    """Plot horizontal competitor timeline showing pit re-entry and traffic wake."""
    model = (
        pit_loss_model
        if pit_loss_model is not None
        else PitLossModel(race_state.circuit.to_pit_profile())
    )
    race_state.get_driver(target_driver_id)
    window = race_state.predict_pit_rejoin(target_driver_id, pit_loss_model=model)

    proj_gap = window["projected_gap_to_leader"]
    pit_loss = window["pit_loss_seconds"]

    fig = go.Figure()

    active_drivers = [d for d in race_state.get_standings() if not d.is_retired]
    for d in active_drivers:
        color = "#a1a1aa" if d.driver_id != target_driver_id else "#38bdf8"
        size = 10 if d.driver_id != target_driver_id else 14
        comp_hover = f"<b>{d.driver_id}</b> ({d.team})<br>Gap to P1: +%{{x:.2f}}s<extra></extra>"
        fig.add_trace(
            go.Scatter(
                x=[d.gap_to_leader],
                y=[f"P{d.position} {d.driver_id}"],
                mode="markers+text",
                name=d.driver_id,
                text=[f"+{d.gap_to_leader:.1f}s"],
                textposition="middle right",
                marker=dict(color=color, size=size),
                showlegend=False,
                hovertemplate=comp_hover,
            )
        )

    rejoin_pos = window["projected_position"]
    rejoin_hover = (
        "<b>Re-entry Projected</b><br>"
        f"Position: P{rejoin_pos}<br>"
        f"Gap: +{proj_gap:.2f}s<br>"
        f"Pit Loss: {pit_loss:.1f}s<extra></extra>"
    )
    fig.add_trace(
        go.Scatter(
            x=[proj_gap],
            y=[f"P{rejoin_pos} [REJOIN]"],
            mode="markers+text",
            name="Projected Re-entry",
            text=[f"REJOIN (+{proj_gap:.1f}s)"],
            textposition="middle right",
            marker=dict(color="#06b6d4", size=16, symbol="diamond"),
            showlegend=False,
            hovertemplate=rejoin_hover,
        )
    )

    gap_ahead = window["gap_to_car_ahead"]
    if gap_ahead is not None and gap_ahead < 1.5:
        car_ahead_gap = proj_gap - gap_ahead
        fig.add_vrect(
            x0=car_ahead_gap,
            x1=car_ahead_gap + 1.5,
            fillcolor="rgba(239, 68, 68, 0.15)",
            layer="below",
            line_width=1,
            line_color="rgba(239, 68, 68, 0.4)",
            annotation_text="Dirty Air Wake (<1.5s)",
            annotation_position="top left",
        )

    layout = get_base_layout(is_dark)
    layout.update(
        title=dict(
            text=f"Pit Window Clearance Timeline (Loss: {pit_loss:.1f}s)", font=dict(size=13)
        ),
        xaxis_title="Gap to Race Leader (Seconds)",
        yaxis=dict(autorange="reversed"),
        height=320,
    )
    fig.update_layout(**layout)
    return fig


def plot_1stop_optimization_curve(
    circuit: CircuitConfig,
    compound1: TyreCompound = TyreCompound.MEDIUM,
    compound2: TyreCompound = TyreCompound.HARD,
    track_temp: float = 35.0,
    is_dark: bool = True,
) -> go.Figure:
    """Plot total race time sweep across all feasible pit stop laps."""
    evaluator = StrategyEvaluator(circuit)
    total_laps = circuit.total_laps

    pit_laps: list[int] = []
    total_times: list[float] = []

    best_lap, best_res = evaluator.optimize_1stop(compound1, compound2, track_temp=track_temp)

    for lap in range(5, total_laps - 4):
        p = StrategyPlan(
            stints=(
                StintPlan(compound=compound1, lap_count=lap),
                StintPlan(compound=compound2, lap_count=total_laps - lap),
            )
        )
        res = evaluator.evaluate_strategy(p, track_temp=track_temp)
        pit_laps.append(lap)
        total_times.append(res.total_race_time)

    min_time = min(total_times)
    deltas = [t - min_time for t in total_times]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=pit_laps,
            y=deltas,
            mode="lines",
            name="Race Time Penalty vs Optimal",
            line=dict(color="#06b6d4", width=2.5),
            hovertemplate="Pit Lap: %{x}<br>Time Delta: +%{y:.2f}s<extra></extra>",
        )
    )

    opt_hover = (
        f"<b>Optimal Pit Window: Lap {best_lap}</b><br>"
        f"Total Time: {best_res.total_race_time:.1f}s<extra></extra>"
    )
    fig.add_trace(
        go.Scatter(
            x=[best_lap],
            y=[0.0],
            mode="markers+text",
            name="Optimal Pit Lap",
            text=[f"Optimal: Lap {best_lap}"],
            textposition="top center",
            marker=dict(color="#eab308", size=14, symbol="star"),
            hovertemplate=opt_hover,
        )
    )

    layout = get_base_layout(is_dark)
    layout.update(
        title=dict(
            text=f"1-Stop Pit Window Optimization ({compound1.value} -> {compound2.value})",
            font=dict(size=13),
        ),
        xaxis_title="Pit Stop Lap Number",
        yaxis_title="Delta to Optimal Race Time (Seconds)",
    )
    fig.update_layout(**layout)
    return fig


def plot_strategy_comparison(
    comparisons: list[dict[str, Any]],
    is_dark: bool = True,
) -> go.Figure:
    """Plot bar chart comparing candidate race strategies."""
    names = [c["strategy_name"] for c in comparisons]
    deltas = [c["delta_to_fastest_seconds"] for c in comparisons]
    colors = ["#22c55e" if d == 0.0 else "#06b6d4" for d in deltas]

    bar_texts = [
        f"FASTEST ({c['total_time_seconds']:.1f}s)" if d == 0.0 else f"+{d:.2f}s"
        for d, c in zip(deltas, comparisons, strict=False)
    ]

    fig = go.Figure(
        go.Bar(
            y=names,
            x=deltas,
            orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(255,255,255,0.1)", width=1)),
            text=bar_texts,
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Delta: +%{x:.2f}s<extra></extra>",
        )
    )

    layout = get_base_layout(is_dark)
    layout.update(
        title=dict(text="Candidate Strategy Time Deltas (vs Fastest)", font=dict(size=13)),
        xaxis_title="Time Delta (Seconds Behind Fastest Strategy)",
        yaxis=dict(autorange="reversed"),
        height=260,
    )
    fig.update_layout(**layout)
    return fig


def plot_confidence_gauge(confidence_pct: int = 78, is_dark: bool = True) -> go.Figure:
    """Plot circular radial confidence gauge matching the reference design."""
    fig = go.Figure(
        go.Pie(
            values=[confidence_pct, 100 - confidence_pct],
            hole=0.76,
            marker=dict(colors=["#10b981", "rgba(255,255,255,0.06)"]),
            textinfo="none",
            hoverinfo="none",
            sort=False,
            direction="clockwise",
        )
    )
    fig.update_layout(
        annotations=[
            dict(
                text=f"<b>{confidence_pct}%</b>",
                x=0.5,
                y=0.5,
                font=dict(size=26, color="#f8fafc", family="DM Sans, sans-serif"),
                showarrow=False,
            )
        ],
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=5, r=5, t=5, b=5),
        height=150,
    )
    return fig


def plot_sakhir_circuit_map(is_dark: bool = True) -> go.Figure:
    """Plot interactive circuit track map of Bahrain International Circuit (Sakhir)."""
    # Normalized coordinates representing the layout of Bahrain Sakhir GP Track
    # Loop begins on the Start/Finish straight and proceeds through Turns 1 to 15
    pts = [
        # Main Straight
        (180, 80),
        (180, 200),
        (180, 320),
        (180, 450),
        (180, 580),
        (180, 680),
        # Turn 1 Hairpin right
        (190, 720),
        (220, 750),
        (260, 760),
        (300, 740),
        # Turn 2 flick left
        (330, 715),
        (360, 700),
        # Turn 3 right onto uphill run
        (390, 710),
        (430, 730),
        (480, 750),
        # Straight to Turn 4
        (540, 770),
        (600, 785),
        (660, 795),
        (710, 800),
        # Turn 4 sharp right-hander
        (750, 790),
        (770, 760),
        (765, 720),
        (740, 680),
        # Esses Turns 5, 6, 7 downhill
        (710, 640),
        (680, 590),
        (660, 540),
        (650, 480),
        # Turn 8 right hairpin
        (660, 440),
        (690, 420),
        (700, 390),
        (680, 360),
        (640, 340),
        # Turns 9 & 10 blind left downhill
        (580, 320),
        (520, 290),
        (460, 250),
        (420, 210),
        (400, 160),
        # Back straight towards Turn 11
        (395, 120),
        (390, 70),
        (370, 40),
        # Turn 11 fast left
        (330, 30),
        (290, 35),
        # Turns 12 & 13 sweeping right
        (250, 50),
        (220, 70),
        (180, 80),
    ]

    x_vals = [p[0] for p in pts]
    y_vals = [p[1] for p in pts]

    fig = go.Figure()

    # Track Base Outline
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines",
            line=dict(color="#334155", width=6),
            hoverinfo="none",
            showlegend=False,
        )
    )

    # Track Center Line (Cyan / Blue Gradient aesthetic)
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines",
            line=dict(color="#38bdf8", width=2.5),
            hoverinfo="none",
            showlegend=False,
        )
    )

    # DRS Zones (Main straight, run to T4, back straight)
    drs_zones = [
        # DRS Zone 1: Main Straight (y: 120 to 650)
        ([180, 180], [120, 650], "DRS Zone 1"),
        # DRS Zone 2: Run to T4
        ([450, 700], [735, 795], "DRS Zone 2"),
        # DRS Zone 3: T10 to T11
        ([400, 385], [210, 70], "DRS Zone 3"),
    ]
    for drs_x, drs_y, drs_name in drs_zones:
        fig.add_trace(
            go.Scatter(
                x=drs_x,
                y=drs_y,
                mode="lines",
                line=dict(color="#06b6d4", width=4.5),
                name="DRS Zone",
                hoverinfo="text",
                hovertext=f"<b>{drs_name}</b>",
                showlegend=False,
            )
        )

    # Corner Number Annotations (1, 4, 8, 10, 11, 14, 15)
    corners = [
        (260, 785, "1"),
        (785, 790, "4"),
        (715, 415, "8"),
        (405, 185, "10"),
        (280, 20, "11"),
        (205, 50, "14"),
        (160, 80, "15"),
    ]
    for cx, cy, c_lbl in corners:
        fig.add_annotation(
            x=cx,
            y=cy,
            text=f"<b>{c_lbl}</b>",
            showarrow=False,
            font=dict(size=9, color="#94a3b8", family="DM Sans"),
        )

    # Competitor & Car Marker Positions on Track
    fig.add_trace(
        go.Scatter(
            x=[180],
            y=[480],
            mode="markers+text",
            name="Our car",
            text=["Our car"],
            textposition="middle left",
            textfont=dict(color="#38bdf8", size=10),
            marker=dict(color="#38bdf8", size=12, line=dict(color="#ffffff", width=1.5)),
            hoverinfo="text",
            hovertext="<b>STRATOS (Our Car)</b> - P4 (Gap: +1.24s)",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[540],
            y=[770],
            mode="markers+text",
            name="Teammate",
            text=["Teammate"],
            textposition="top center",
            textfont=dict(color="#22c55e", size=10),
            marker=dict(color="#22c55e", size=10),
            hoverinfo="text",
            hovertext="<b>Teammate</b> - P7",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[180],
            y=[620],
            mode="markers+text",
            name="Rival",
            text=["Rival (VER)"],
            textposition="middle left",
            textfont=dict(color="#ef4444", size=10),
            marker=dict(color="#ef4444", size=10),
            hoverinfo="text",
            hovertext="<b>Rival: VER</b> - P1",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[180],
            y=[140],
            mode="markers",
            name="Pit stop",
            marker=dict(
                color="#0f172a", size=10, symbol="square", line=dict(color="#94a3b8", width=1.5)
            ),
            hoverinfo="text",
            hovertext="<b>Pit Lane Entry</b>",
        )
    )

    # North Indicator
    fig.add_annotation(
        x=820,
        y=150,
        text="<b>N</b><br>▲",
        showarrow=False,
        font=dict(size=11, color="#64748b", family="DM Sans"),
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(visible=False, range=[120, 880]),
        yaxis=dict(visible=False, range=[-10, 850], scaleanchor="x", scaleratio=1),
        legend=dict(
            orientation="v",
            x=0.72,
            y=0.95,
            bgcolor="rgba(15,23,42,0.7)",
            bordercolor="rgba(255,255,255,0.08)",
            borderwidth=1,
            font=dict(size=9, color="#94a3b8"),
        ),
        height=320,
    )
    return fig


def plot_degradation_predicted_vs_actual(is_dark: bool = True) -> go.Figure:
    """Plot Predicted vs Actual tyre degradation curves with shaded uncertainty bands."""
    fig = go.Figure()
    laps = np.arange(0, 29)

    # Soft Compound (red)
    soft_base = 92.5 + 0.18 * laps + 0.008 * (laps**2)
    soft_upper = soft_base + 0.65
    soft_lower = soft_base - 0.65

    # Medium Compound (yellow)
    med_base = 93.4 + 0.09 * laps + 0.003 * (laps**2)
    med_upper = med_base + 0.50
    med_lower = med_base - 0.50

    # Hard Compound (cyan/white)
    hard_base = 94.6 + 0.05 * laps + 0.001 * (laps**2)
    hard_upper = hard_base + 0.45
    hard_lower = hard_base - 0.45

    # Soft Shaded Band
    fig.add_trace(
        go.Scatter(
            x=list(laps) + list(laps[::-1]),
            y=list(soft_upper) + list(soft_lower[::-1]),
            fill="toself",
            fillcolor="rgba(239,68,68,0.12)",
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="none",
            showlegend=False,
            name="Soft Band",
        )
    )

    # Soft Curve
    fig.add_trace(
        go.Scatter(
            x=laps,
            y=soft_base,
            mode="lines",
            name="Soft",
            line=dict(color="#ef4444", width=2.5),
            hovertemplate="Soft Pred: %{y:.2f}s (Lap %{x})<extra></extra>",
        )
    )

    # Medium Shaded Band
    fig.add_trace(
        go.Scatter(
            x=list(laps) + list(laps[::-1]),
            y=list(med_upper) + list(med_lower[::-1]),
            fill="toself",
            fillcolor="rgba(234,179,8,0.12)",
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="none",
            showlegend=False,
            name="Medium Band",
        )
    )

    # Medium Curve
    fig.add_trace(
        go.Scatter(
            x=laps,
            y=med_base,
            mode="lines",
            name="Medium",
            line=dict(color="#eab308", width=2.5),
            hovertemplate="Medium Pred: %{y:.2f}s (Lap %{x})<extra></extra>",
        )
    )

    # Hard Shaded Band
    fig.add_trace(
        go.Scatter(
            x=list(laps) + list(laps[::-1]),
            y=list(hard_upper) + list(hard_lower[::-1]),
            fill="toself",
            fillcolor="rgba(56,189,248,0.12)",
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="none",
            showlegend=False,
            name="Hard Band",
        )
    )

    # Hard Curve
    fig.add_trace(
        go.Scatter(
            x=laps,
            y=hard_base,
            mode="lines",
            name="Hard",
            line=dict(color="#38bdf8", width=2.5),
            hovertemplate="Hard Pred: %{y:.2f}s (Lap %{x})<extra></extra>",
        )
    )

    # Scatter dots: Actual Telemetry
    np.random.seed(42)
    # Actual Medium telemetry points for our car
    med_actual_laps = np.arange(1, 23)
    med_actual_times = (
        93.4
        + 0.09 * med_actual_laps
        + 0.003 * (med_actual_laps**2)
        + np.random.normal(0, 0.28, len(med_actual_laps))
    )

    # Some Soft early stint points
    soft_actual_laps = np.arange(1, 16)
    soft_actual_times = (
        92.5
        + 0.18 * soft_actual_laps
        + 0.008 * (soft_actual_laps**2)
        + np.random.normal(0, 0.35, len(soft_actual_laps))
    )

    fig.add_trace(
        go.Scatter(
            x=list(med_actual_laps) + list(soft_actual_laps),
            y=list(med_actual_times) + list(soft_actual_times),
            mode="markers",
            name="Actual",
            marker=dict(color="#f8fafc", size=4.5, opacity=0.75),
            hovertemplate="Actual Telemetry: %{y:.2f}s (Lap %{x})<extra></extra>",
        )
    )

    layout = get_base_layout(is_dark)
    layout.update(
        xaxis=dict(title="Tyre Age (Laps)", range=[0, 28], dtick=5),
        yaxis=dict(title="Lap Time (s)", range=[90, 110], dtick=5),
        height=320,
        legend=dict(
            orientation="h",
            x=0.5,
            y=1.12,
            xanchor="center",
            font=dict(size=10, color="#94a3b8"),
        ),
        margin=dict(l=40, r=20, t=35, b=40),
    )
    fig.update_layout(**layout)
    return fig


def plot_multi_season_strategy_distribution(
    distribution: list[dict[str, Any]],
    is_dark: bool = True,
) -> go.Figure:
    """Plot stacked bar chart of winning pit stop strategies by season (2021-2026)."""
    fig = go.Figure()
    seasons = [d["season"] for d in distribution]
    one_stops = [d["1_stop"] for d in distribution]
    two_stops = [d["2_stop"] for d in distribution]
    three_plus = [d["3_plus_stop"] for d in distribution]

    fig.add_trace(
        go.Bar(
            x=seasons,
            y=one_stops,
            name="1-Stop Strategy",
            marker_color="#10b981",
            hovertemplate="Season %{x}<br>1-Stop Wins: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=seasons,
            y=two_stops,
            name="2-Stop Strategy",
            marker_color="#38bdf8",
            hovertemplate="Season %{x}<br>2-Stop Wins: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=seasons,
            y=three_plus,
            name="3+ Stop / Wet",
            marker_color="#a855f7",
            hovertemplate="Season %{x}<br>3+ Stop Wins: %{y}<extra></extra>",
        )
    )

    layout = get_base_layout(is_dark)
    layout.update(
        barmode="stack",
        height=280,
        title=dict(
            text="Winning Strategy Frequency Across Seasons (2021–2026)",
            font=dict(size=12, color="#ffffff" if is_dark else "#0f172a"),
        ),
        xaxis=dict(title="Championship Season", tickfont=dict(size=11)),
        yaxis=dict(title="Grand Prix Wins", dtick=2),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(
            orientation="h",
            x=0.5,
            y=1.15,
            xanchor="center",
            font=dict(size=10, color="#94a3b8"),
        ),
    )
    fig.update_layout(**layout)
    return fig

