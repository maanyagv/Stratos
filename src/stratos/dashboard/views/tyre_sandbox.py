"""Tyre degradation and compound wear sandbox view for STRATOS dashboard."""

from __future__ import annotations

import streamlit as st

from stratos.dashboard.charts import plot_tyre_degradation_curves
from stratos.models.tyre import DEFAULT_COMPOUND_PARAMS, TyreCompound, TyreDegradationModel


def render_tyre_sandbox_view(is_dark: bool = True) -> None:
    """Render the interactive tyre degradation sandbox."""
    st.markdown("### 🛞 Tyre Compound Degradation Sandbox")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.25rem;'>"
        "Explore non-linear degradation kinetics, thermal operating window penalties, and "
        "cliff wear thresholds across Pirelli Formula 1 compounds."
        "</p>",
        unsafe_allow_html=True,
    )

    # Sandbox Controls
    c1, c2, c3 = st.columns(3)
    with c1:
        track_temp = st.slider(
            "Track Surface Temperature (°C)",
            min_value=15.0,
            max_value=55.0,
            value=35.0,
            step=1.0,
        )
    with c2:
        max_laps = st.slider(
            "Evaluation Horizon (Laps)",
            min_value=20,
            max_value=60,
            value=45,
            step=5,
        )
    with c3:
        st.markdown("<div style='height: 1.6rem;'></div>", unsafe_allow_html=True)
        st.caption("Thermal wear penalties apply when track temp exceeds optimal window.")

    # Tyre Model
    tyre_model = TyreDegradationModel()

    # Compound KPI Cards
    s_col, m_col, h_col = st.columns(3)
    p_soft = DEFAULT_COMPOUND_PARAMS[TyreCompound.SOFT]
    p_med = DEFAULT_COMPOUND_PARAMS[TyreCompound.MEDIUM]
    p_hard = DEFAULT_COMPOUND_PARAMS[TyreCompound.HARD]

    with s_col:
        deg20_s = tyre_model.lap_time_penalty(TyreCompound.SOFT, 20, track_temp=track_temp)
        st.markdown(
            f"""
        <div class="metric-card" style="border-top: 3px solid #ef4444;">
            <div class="metric-label" style="color: #ef4444;">SOFT COMPOUND (C5/C4)</div>
            <div class="metric-value">
                +{p_soft.linear_deg:.3f}
                <span style="font-size: 0.95rem; color: var(--text-muted);">s/lap</span>
            </div>
            <div class="metric-delta delta-red">
                Cliff: Lap {p_soft.cliff_threshold} &bull; L20 Deg: +{deg20_s:.2f}s
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m_col:
        deg20_m = tyre_model.lap_time_penalty(TyreCompound.MEDIUM, 20, track_temp=track_temp)
        st.markdown(
            f"""
        <div class="metric-card" style="border-top: 3px solid #eab308;">
            <div class="metric-label" style="color: #eab308;">MEDIUM COMPOUND (C3)</div>
            <div class="metric-value">
                +{p_med.linear_deg:.3f}
                <span style="font-size: 0.95rem; color: var(--text-muted);">s/lap</span>
            </div>
            <div class="metric-delta delta-amber">
                Cliff: Lap {p_med.cliff_threshold} &bull; L20 Deg: +{deg20_m:.2f}s
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with h_col:
        deg20_h = tyre_model.lap_time_penalty(TyreCompound.HARD, 20, track_temp=track_temp)
        st.markdown(
            f"""
        <div class="metric-card" style="border-top: 3px solid #f8fafc;">
            <div class="metric-label" style="color: #a1a1aa;">HARD COMPOUND (C2/C1)</div>
            <div class="metric-value">
                +{p_hard.linear_deg:.3f}
                <span style="font-size: 0.95rem; color: var(--text-muted);">s/lap</span>
            </div>
            <div class="metric-delta delta-green">
                Cliff: Lap {p_hard.cliff_threshold} &bull; L20 Deg: +{deg20_h:.2f}s
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

    # Main Degradation Plot
    st.markdown(
        """
    <div class="chart-wrap">
        <div class="chart-title">
            Non-Linear Compound Degradation & Operating Window Sensitivity
        </div>
        <div class="chart-subtitle">
            Calculated lap time wear delta (+s/lap) combining pace offset,
            linear wear, and cliff escalation
        </div>
    """,
        unsafe_allow_html=True,
    )

    fig = plot_tyre_degradation_curves(
        tyre_model=tyre_model,
        max_laps=max_laps,
        track_temp=track_temp,
        is_dark=is_dark,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    # Stint Comparison Table
    st.markdown("#### Tabular Stint Wear Matrix")
    laps_sample = [1, 5, 10, 15, 20, 25, 30, 35, 40]
    table_rows = ""
    for lap in laps_sample:
        if lap <= max_laps:
            ds = tyre_model.lap_time_penalty(TyreCompound.SOFT, lap, track_temp)
            dm = tyre_model.lap_time_penalty(TyreCompound.MEDIUM, lap, track_temp)
            dh = tyre_model.lap_time_penalty(TyreCompound.HARD, lap, track_temp)
            s_cliff = (
                "<span style='color: #ef4444;'>CLIFF</span>"
                if lap > p_soft.cliff_threshold
                else "OK"
            )
            m_cliff = (
                "<span style='color: #ef4444;'>CLIFF</span>"
                if lap > p_med.cliff_threshold
                else "OK"
            )
            h_cliff = (
                "<span style='color: #ef4444;'>CLIFF</span>"
                if lap > p_hard.cliff_threshold
                else "OK"
            )
            table_rows += f"""
            <tr>
                <td><strong>Lap {lap}</strong></td>
                <td>+{ds:.2f}s ({s_cliff})</td>
                <td>+{dm:.2f}s ({m_cliff})</td>
                <td>+{dh:.2f}s ({h_cliff})</td>
                <td>{dh - ds:+.2f}s</td>
            </tr>
            """

    st.markdown(
        f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>Stint Age</th>
                <th>Soft Penalty</th>
                <th>Medium Penalty</th>
                <th>Hard Penalty</th>
                <th>Hard vs Soft Delta</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    """,
        unsafe_allow_html=True,
    )
