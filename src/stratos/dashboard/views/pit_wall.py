"""Pit Wall multi-agent deliberation view for STRATOS dashboard."""

from __future__ import annotations

import streamlit as st

from stratos.agents.base import AgentUrgency
from stratos.agents.team import STRATOSStrategyTeam
from stratos.models.pit import TrackStatus
from stratos.models.state import (
    CircuitConfig,
    DriverState,
    EnvironmentState,
    RaceState,
)
from stratos.models.tyre import TyreCompound


def render_pit_wall_view(is_dark: bool = True) -> None:
    """Render the deliberative pit wall tab."""
    st.markdown("### 🏎️ Deliberative Multi-Agent Pit Wall")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.25rem;'>"
        "Specialist AI agents (Weather, Competitor, Risk) deliberate in real-time, "
        "arbitrated by the Strategic Synthesis Agent to issue Pareto-optimal race directives."
        "</p>",
        unsafe_allow_html=True,
    )

    # Interactive Scenario Controls (Sidebar / Expander)
    with st.expander("⚙️ Scenario Tuning & Pit Wall Telemetry Controls", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            circuit_choice = st.selectbox(
                "Circuit",
                ["Silverstone", "Monaco", "Spa-Francorchamps", "Monza"],
                index=0,
                key="pw_circuit_choice",
            )
        with c2:
            track_status_str = st.selectbox(
                "Track Status",
                ["GREEN", "VSC", "SAFETY_CAR", "YELLOW"],
                index=0,
                key="pw_track_status",
            )
        with c3:
            rainfall_val = st.slider(
                "Rainfall (mm/h)",
                0.0,
                3.5,
                0.0,
                step=0.1,
                key="pw_rainfall_val",
            )
        with c4:
            interval_val = st.slider(
                "Interval to Rival (s)",
                0.5,
                6.0,
                1.8,
                step=0.1,
                key="pw_interval_val",
            )

    # Build active race state based on selections
    circuits = {
        "Silverstone": CircuitConfig("Silverstone", 52, 88.0, 25.6, overtaking_difficulty=0.45),
        "Monaco": CircuitConfig("Monaco", 78, 74.0, 21.8, overtaking_difficulty=0.95),
        "Spa-Francorchamps": CircuitConfig("Spa", 44, 104.0, 19.2, overtaking_difficulty=0.35),
        "Monza": CircuitConfig("Monza", 53, 81.0, 21.5, overtaking_difficulty=0.25),
    }
    circuit = circuits[circuit_choice]
    track_status = TrackStatus.from_string(track_status_str)

    env = EnvironmentState(
        lap=20,
        total_laps=circuit.total_laps,
        track_status=track_status,
        rainfall_intensity=rainfall_val,
        track_temp=35.0,
    )

    drivers = {
        "VER": DriverState("VER", "Red Bull", 1, 0.0, 0.0, TyreCompound.MEDIUM, tyre_age=20),
        "NOR": DriverState(
            "NOR", "McLaren", 2, interval_val, interval_val, TyreCompound.MEDIUM, tyre_age=20
        ),
        "LEC": DriverState("LEC", "Ferrari", 3, 14.5, 12.7, TyreCompound.HARD, tyre_age=20),
    }
    if circuit_choice == "Monaco":
        # Add backmarker in pit window for traffic testing
        drivers["BOT"] = DriverState("BOT", "Sauber", 15, 25.4, 1.0, TyreCompound.HARD, tyre_age=20)

    race_state = RaceState(circuit, env, drivers)
    target_driver = "NOR"

    # Run Multi-Agent Team
    team = STRATOSStrategyTeam()
    synthesis = team.evaluate_turn(race_state, target_driver_id=target_driver)

    # 1. KPI Top Row
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Track Status</div>
            <div class="metric-value">{track_status.value}</div>
            <div class="metric-delta delta-cyan">● Active Caution Floor</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with k2:
        rain_cls = (
            "delta-red"
            if rainfall_val >= 2.0
            else ("delta-amber" if rainfall_val >= 0.3 else "delta-green")
        )
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Precipitation</div>
            <div class="metric-value">
                {rainfall_val:.1f}
                <span style="font-size: 1rem; color: var(--text-muted);">mm/h</span>
            </div>
            <div class="metric-delta {rain_cls}">Crossover: 0.3 mm/h</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with k3:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Gap to Leader (VER)</div>
            <div class="metric-value">
                +{interval_val:.2f}
                <span style="font-size: 1rem; color: var(--text-muted);">s</span>
            </div>
            <div class="metric-delta delta-cyan">Undercut Window: &le;2.5s</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with k4:
        urg_cls = (
            "delta-red"
            if synthesis.urgency == AgentUrgency.CRITICAL
            else ("delta-amber" if synthesis.urgency == AgentUrgency.HIGH else "delta-green")
        )
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Consensus Action</div>
            <div class="metric-value" style="font-size: 1.20rem;">
                {synthesis.primary_action.value}
            </div>
            <div class="metric-delta {urg_cls}">Urgency: {synthesis.urgency.value}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)

    # 2. Radio Command Banner
    st.markdown(
        f"""
    <div class="radio-banner">
        <div class="radio-icon">📻</div>
        <div class="radio-content">
            <div class="radio-title">Pit Wall Radio &bull; Target: {target_driver}</div>
            <div class="radio-call">"{synthesis.executive_summary}"</div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # 3. Specialist Agent Deliberation Cards (Grid of 3)
    st.markdown("#### Specialist Agent Deliberation")
    a1, a2, a3 = st.columns(3)

    reports = synthesis.agent_reports
    weather_rep = reports.get("WeatherAgent")
    comp_rep = reports.get("CompetitorAgent")
    risk_rep = reports.get("RiskAgent")

    with a1:
        if weather_rep:
            comp_badge = (
                f"<span class='badge badge-intermediate'>"
                f"{weather_rep.suggested_compound.value}</span>"
                if weather_rep.suggested_compound
                else ""
            )
            st.markdown(
                f"""
            <div class="agent-card">
                <div>
                    <div class="agent-header">
                        <div class="agent-name">🌦️ Weather Agent</div>
                        <span class="badge badge-low">Conf: {weather_rep.confidence:.2f}</span>
                    </div>
                    <div class="agent-recommendation" style="color: #06b6d4;">
                        {weather_rep.recommendation.value} {comp_badge}
                    </div>
                    <div class="agent-rationale">{weather_rep.rationale}</div>
                </div>
                <div>
                    <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.5rem;">
                        Track Temp: {env.track_temp:.1f}°C &bull;
                        Rain: {env.rainfall_intensity:.1f} mm/h
                    </div>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

    with a2:
        if comp_rep:
            comp_badge = (
                f"<span class='badge badge-hard'>{comp_rep.suggested_compound.value}</span>"
                if comp_rep.suggested_compound
                else ""
            )
            st.markdown(
                f"""
            <div class="agent-card">
                <div>
                    <div class="agent-header">
                        <div class="agent-name">⚔️ Competitor Agent</div>
                        <span class="badge badge-high">Conf: {comp_rep.confidence:.2f}</span>
                    </div>
                    <div class="agent-recommendation" style="color: #eab308;">
                        {comp_rep.recommendation.value} {comp_badge}
                    </div>
                    <div class="agent-rationale">{comp_rep.rationale}</div>
                </div>
                <div>
                    <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.5rem;">
                        Target Rival: VER (+{interval_val:.2f}s) &bull;
                        Threat: {comp_rep.risk_score:.2f}
                    </div>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

    with a3:
        if risk_rep:
            risk_badge_cls = "badge-critical" if risk_rep.risk_score >= 0.7 else "badge-low"
            sc_prob = risk_rep.metrics.get("circuit_sc_probability", 0.0)
            in_traf = risk_rep.metrics.get("in_traffic_post_pit", False)
            st.markdown(
                f"""
            <div class="agent-card">
                <div>
                    <div class="agent-header">
                        <div class="agent-name">🛡️ Risk Agent</div>
                        <span class="badge {risk_badge_cls}">Risk: {risk_rep.risk_score:.2f}</span>
                    </div>
                    <div class="agent-recommendation" style="color: #ef4444;">
                        {risk_rep.recommendation.value}
                    </div>
                    <div class="agent-rationale">{risk_rep.rationale}</div>
                </div>
                <div>
                    <div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 0.5rem;">
                        SC Hazard: {sc_prob:.2f} &bull; Traffic: {in_traf}
                    </div>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # 4. Lead Strategist Arbitration Box
    chosen_str = (
        f"Fit {synthesis.chosen_compound.value}" if synthesis.chosen_compound else "Extend on Track"
    )
    alt_str = (
        synthesis.alternative_action.value
        if synthesis.alternative_action
        else "Maintain Delta Pace"
    )
    st.markdown(
        f"""
    <div class="chart-wrap" style="border-left: 3px solid #22c55e;">
        <div class="chart-title">⚖️ Strategic Synthesis & Deliberative Arbitration</div>
        <div class="chart-subtitle">
            Consensus resolved across conflicting meteorological, tactical, and traffic constraints
        </div>
        <p style="font-size: 0.84rem; color: var(--text); line-height: 1.5; margin-top: 0.5rem;">
            {synthesis.deliberative_rationale}
        </p>
        <div style="display: flex; gap: 1.5rem; margin-top: 0.8rem; font-size: 0.78rem;
                    color: var(--text-muted); flex-wrap: wrap;">
            <div>
                <strong>Primary Mandate:</strong>
                <span style="color: #22c55e;">
                    {synthesis.primary_action.value} ({chosen_str})
                </span>
            </div>
            <div>
                <strong>Tactical Fallback:</strong>
                <span style="color: #eab308;">{alt_str}</span>
            </div>
            <div>
                <strong>Composite Risk:</strong> {synthesis.composite_risk:.2f}
            </div>
            <div>
                <strong>Synthesis Confidence:</strong> {synthesis.confidence * 100:.0f}%
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
