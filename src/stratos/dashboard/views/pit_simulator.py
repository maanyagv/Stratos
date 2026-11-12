"""Pit window clearance and undercut simulator view for STRATOS dashboard."""

from __future__ import annotations

import streamlit as st

from stratos.dashboard.charts import plot_pit_window_rejoin
from stratos.models.pit import (
    CIRCUIT_PIT_PROFILES,
    PitLossModel,
    TrackStatus,
)
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    RaceState,
)
from stratos.models.tyre import TyreCompound


def render_pit_simulator_view(is_dark: bool = True) -> None:
    """Render the pit window and undercut simulator tab."""
    st.markdown("### ⏱️ Pit Window & Undercut Re-entry Simulator")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.25rem;'>"
        "Model pit lane speed limit transit, stationary stop duration, VSC / SC time savings, "
        "and project re-entry track positions into competitor dirty air wakes."
        "</p>",
        unsafe_allow_html=True,
    )

    # Simulator Controls
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        circuit_key = st.selectbox(
            "Circuit Profile",
            ["monaco", "silverstone", "monza", "spa", "red_bull_ring"],
            format_func=lambda k: CIRCUIT_PIT_PROFILES[k].circuit_name,
            index=1,
        )
    with c2:
        status_choice = st.selectbox(
            "Track Status Condition",
            ["GREEN", "VSC", "SAFETY_CAR"],
            index=0,
        )
    with c3:
        target_gap = st.slider(
            "Driver Current Gap to P1 (s)",
            min_value=0.0,
            max_value=35.0,
            value=0.0,
            step=0.5,
        )
    with c4:
        box_time = st.slider(
            "Stationary Box Time (s)",
            min_value=1.8,
            max_value=6.0,
            value=2.4,
            step=0.1,
        )

    profile = CIRCUIT_PIT_PROFILES[circuit_key]
    status = TrackStatus.from_string(status_choice)
    pit_model = PitLossModel(profile)
    pit_loss = pit_model.calculate_pit_loss(track_status=status, stationary_time=box_time)

    # Mock Grid for Demonstration
    circuit = CircuitConfig(
        name=profile.circuit_name,
        total_laps=52,
        base_lap_time=88.0,
        pit_transit_loss_green=profile.pit_transit_loss_green,
    )
    env = EnvironmentState(lap=20, total_laps=52, track_status=status)

    drivers = {
        "TARGET": DriverState(
            "TARGET",
            "Target Car",
            1 if target_gap == 0.0 else 2,
            target_gap,
            target_gap,
            TyreCompound.MEDIUM,
            tyre_age=20,
        ),
        "NOR": DriverState("NOR", "McLaren", 2, 4.5, 4.5, TyreCompound.MEDIUM, tyre_age=20),
        "LEC": DriverState("LEC", "Ferrari", 3, 14.0, 9.5, TyreCompound.HARD, tyre_age=20),
        "HAM": DriverState("HAM", "Mercedes", 4, 21.0, 7.0, TyreCompound.HARD, tyre_age=20),
        "PIA": DriverState("PIA", "McLaren", 5, 29.5, 8.5, TyreCompound.HARD, tyre_age=20),
        "SAI": DriverState("SAI", "Ferrari", 6, 36.0, 6.5, TyreCompound.HARD, tyre_age=20),
    }

    race_state = RaceState(circuit, env, drivers)
    window = pit_model.evaluate_pit_window(
        target_driver_gap_to_leader=target_gap,
        competitor_gaps=[
            {"driver_id": d.driver_id, "position": d.position, "gap_to_leader": d.gap_to_leader}
            for d in drivers.values()
            if d.driver_id != "TARGET"
        ],
        track_status=status,
        stationary_time=box_time,
    )

    # KPI Summary Cards
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        saved_delta = profile.total_green_pit_loss - pit_loss
        delta_str = (
            f"Saved: {saved_delta:.1f}s vs Green" if saved_delta > 0.5 else "Green Flag Nominal"
        )
        delta_cls = "delta-green" if saved_delta > 0.5 else "delta-cyan"
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Total Pit Loss</div>
            <div class="metric-value">
                {pit_loss:.2f}
                <span style="font-size: 0.95rem; color: var(--text-muted);">s</span>
            </div>
            <div class="metric-delta {delta_cls}">{delta_str}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m2:
        proj_p = window["projected_position"]
        proj_gap_lead = window["projected_gap_to_leader"]
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Projected Re-entry</div>
            <div class="metric-value">P{proj_p}</div>
            <div class="metric-delta delta-cyan">Projected Gap: +{proj_gap_lead:.1f}s</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m3:
        car_ahead_str = window["car_ahead"] or "NONE (Leading)"
        gap_ahead_val = window["gap_to_car_ahead"]
        gap_ahead_str = f"+{gap_ahead_val:.1f}s" if gap_ahead_val is not None else "Clear Air"
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Car Directly Ahead</div>
            <div class="metric-value" style="font-size: 1.35rem;">{car_ahead_str}</div>
            <div class="metric-delta delta-cyan">Gap Ahead: {gap_ahead_str}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m4:
        in_traffic = window["in_traffic"]
        traf_cls = "delta-red" if in_traffic else "delta-green"
        traf_text = "DIRTY AIR TRAFFIC (<1.5s)" if in_traffic else "CLEAN AIR WINDOW"
        traf_val_str = "TRAFFIC" if in_traffic else "CLEAN AIR"
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Traffic Clearance</div>
            <div class="metric-value" style="font-size: 1.25rem;">{traf_val_str}</div>
            <div class="metric-delta {traf_cls}">{traf_text}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

    # Plot Re-entry Timeline
    st.markdown(
        """
    <div class="chart-wrap">
        <div class="chart-title">Dynamic Re-entry Gap Timeline</div>
        <div class="chart-subtitle">
            Competitor spacing relative to race leader, projected exit point,
            and turbulent aerodynamic wake zone
        </div>
    """,
        unsafe_allow_html=True,
    )

    fig = plot_pit_window_rejoin(
        race_state=race_state,
        target_driver_id="TARGET",
        pit_loss_model=pit_model,
        is_dark=is_dark,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    # Circuit Pit Loss Benchmark Table
    st.markdown("#### Formula 1 Circuit Pit Loss Comparison Database")
    bench_rows = ""
    for c_key, c_prof in CIRCUIT_PIT_PROFILES.items():
        if c_key == "default":
            continue
        g_loss = c_prof.total_green_pit_loss
        v_loss = c_prof.total_vsc_pit_loss
        s_loss = c_prof.total_sc_pit_loss
        bench_rows += f"""
        <tr>
            <td><strong>{c_prof.circuit_name}</strong></td>
            <td>{c_prof.pit_speed_limit_kmh:.0f} km/h</td>
            <td>{g_loss:.2f}s</td>
            <td>{v_loss:.2f}s (<span style="color: #22c55e;">-{g_loss - v_loss:.1f}s</span>)</td>
            <td>{s_loss:.2f}s (<span style="color: #22c55e;">-{g_loss - s_loss:.1f}s</span>)</td>
        </tr>
        """

    st.markdown(
        f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>Circuit</th>
                <th>Pit Speed Limit</th>
                <th>Green Flag Pit Loss</th>
                <th>VSC Pit Loss (Savings)</th>
                <th>Safety Car Pit Loss (Savings)</th>
            </tr>
        </thead>
        <tbody>
            {bench_rows}
        </tbody>
    </table>
    """,
        unsafe_allow_html=True,
    )
