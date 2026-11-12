"""Strategy optimization and pit window sweeper view for STRATOS dashboard."""

from __future__ import annotations

import streamlit as st

from stratos.dashboard.charts import (
    plot_1stop_optimization_curve,
    plot_strategy_comparison,
)
from stratos.models.state import CircuitConfig
from stratos.models.strategy import (
    StintPlan,
    StrategyEvaluator,
    StrategyPlan,
)
from stratos.models.tyre import TyreCompound


def render_strategy_optimizer_view(is_dark: bool = True) -> None:
    """Render the strategy optimizer and candidate comparison tab."""
    st.markdown("### 📊 Race Strategy Optimizer & Pit Window Sweeper")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.25rem;'>"
        "Simulate deterministic lap-by-lap pace trajectories incorporating tyre degradation, "
        "fuel mass reduction, track evolution, and FIA mandatory compound regulations."
        "</p>",
        unsafe_allow_html=True,
    )

    # 1. Parameter Tuning Controls
    with st.expander("⚙️ Circuit & Strategy Tuning Parameters", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            circuit_name = st.selectbox(
                "Circuit",
                ["Silverstone", "Monaco", "Spa-Francorchamps", "Monza"],
                index=0,
            )
        with c2:
            track_temp = st.slider(
                "Track Temperature (°C)",
                min_value=15.0,
                max_value=50.0,
                value=35.0,
                step=1.0,
            )
        with c3:
            start_comp_str = st.selectbox(
                "Starting Compound",
                ["MEDIUM", "SOFT", "HARD"],
                index=0,
            )
        with c4:
            finish_comp_str = st.selectbox(
                "Finishing Compound",
                ["HARD", "MEDIUM", "SOFT"],
                index=0,
            )

    circuits = {
        "Silverstone": CircuitConfig(
            name="Silverstone",
            total_laps=52,
            base_lap_time=88.0,
            pit_transit_loss_green=25.6,
            fuel_effect_per_lap=0.035,
            track_evolution_per_lap=0.015,
        ),
        "Monaco": CircuitConfig(
            name="Monaco",
            total_laps=78,
            base_lap_time=74.0,
            pit_transit_loss_green=21.8,
            fuel_effect_per_lap=0.025,
            track_evolution_per_lap=0.012,
        ),
        "Spa-Francorchamps": CircuitConfig(
            name="Spa",
            total_laps=44,
            base_lap_time=104.0,
            pit_transit_loss_green=19.2,
            fuel_effect_per_lap=0.045,
            track_evolution_per_lap=0.018,
        ),
        "Monza": CircuitConfig(
            name="Monza",
            total_laps=53,
            base_lap_time=81.0,
            pit_transit_loss_green=21.5,
            fuel_effect_per_lap=0.030,
            track_evolution_per_lap=0.014,
        ),
    }

    circuit = circuits[circuit_name]
    start_comp = TyreCompound.from_string(start_comp_str)
    finish_comp = TyreCompound.from_string(finish_comp_str)

    evaluator = StrategyEvaluator(circuit)

    # 2. 1-Stop Optimization
    best_lap, best_res = evaluator.optimize_1stop(
        compound1=start_comp,
        compound2=finish_comp,
        track_temp=track_temp,
    )

    # KPI Top Row
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Optimal 1-Stop Pit Lap</div>
            <div class="metric-value">Lap {best_lap}</div>
            <div class="metric-delta delta-cyan">
                Window: L{max(1, best_lap - 2)} - L{min(circuit.total_laps, best_lap + 2)}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with k2:
        minutes = int(best_res.total_race_time // 60)
        seconds = best_res.total_race_time % 60
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Simulated Race Time</div>
            <div class="metric-value">{minutes}m {seconds:.1f}s</div>
            <div class="metric-delta delta-green">Total: {best_res.total_race_time:.1f}s</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with k3:
        comp_cls = "delta-green" if best_res.is_fia_compliant else "delta-red"
        comp_text = "FIA COMPLIANT (2 Dry Sets)" if best_res.is_fia_compliant else "NON-COMPLIANT"
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">FIA Rule Compliance</div>
            <div class="metric-value" style="font-size: 1.25rem;">
                {"LEGAL" if best_res.is_fia_compliant else "ILLEGAL"}
            </div>
            <div class="metric-delta {comp_cls}">{comp_text}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with k4:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Pit Stop Loss (Nominal)</div>
            <div class="metric-value">{best_res.pit_loss_total:.1f}s</div>
            <div class="metric-delta delta-cyan">Transit + 2.4s Stationary Box</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

    # 1-Stop Pit Window Sweep Chart
    st.markdown(
        f"""
    <div class="chart-wrap">
        <div class="chart-title">1-Stop Pit Window Optimization Sweep</div>
        <div class="chart-subtitle">
            Simulated completion time deltas across every feasible pit stop lap
            ({start_comp.value} &rarr; {finish_comp.value})
        </div>
    """,
        unsafe_allow_html=True,
    )
    fig_sweep = plot_1stop_optimization_curve(
        circuit=circuit,
        compound1=start_comp,
        compound2=finish_comp,
        track_temp=track_temp,
        is_dark=is_dark,
    )
    st.plotly_chart(fig_sweep, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # 3. Multi-Strategy Benchmarking Matrix
    st.markdown("#### Candidate Race Strategies Benchmark")

    tot = circuit.total_laps
    opt_m_h_lap, _ = evaluator.optimize_1stop(
        TyreCompound.MEDIUM, TyreCompound.HARD, track_temp=track_temp
    )
    opt_s_h_lap, _ = evaluator.optimize_1stop(
        TyreCompound.SOFT, TyreCompound.HARD, track_temp=track_temp
    )
    opt_h_m_lap, _ = evaluator.optimize_1stop(
        TyreCompound.HARD, TyreCompound.MEDIUM, track_temp=track_temp
    )

    # 2-Stop Stint lengths
    stint1_2stop = max(5, int(tot * 0.28))
    stint2_2stop = max(5, int(tot * 0.36))
    stint3_2stop = tot - stint1_2stop - stint2_2stop

    candidate_plans = [
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=opt_m_h_lap),
                StintPlan(compound=TyreCompound.HARD, lap_count=tot - opt_m_h_lap),
            ),
            name=f"Medium -> Hard (Pit L{opt_m_h_lap})",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.SOFT, lap_count=opt_s_h_lap),
                StintPlan(compound=TyreCompound.HARD, lap_count=tot - opt_s_h_lap),
            ),
            name=f"Soft -> Hard (Pit L{opt_s_h_lap})",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.HARD, lap_count=opt_h_m_lap),
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=tot - opt_h_m_lap),
            ),
            name=f"Hard -> Medium (Pit L{opt_h_m_lap})",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.SOFT, lap_count=stint1_2stop),
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=stint2_2stop),
                StintPlan(compound=TyreCompound.HARD, lap_count=stint3_2stop),
            ),
            name=f"Soft -> Med -> Hard 2-Stop (L{stint1_2stop}, L{stint1_2stop + stint2_2stop})",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.SOFT, lap_count=stint1_2stop),
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=stint2_2stop),
                StintPlan(compound=TyreCompound.SOFT, lap_count=stint3_2stop),
            ),
            name=f"Soft -> Med -> Soft 2-Stop (L{stint1_2stop}, L{stint1_2stop + stint2_2stop})",
        ),
        StrategyPlan(
            stints=(
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=tot // 2),
                StintPlan(compound=TyreCompound.MEDIUM, lap_count=tot - (tot // 2)),
            ),
            name="Medium -> Medium [FIA Illegal: 1 Dry Compound]",
        ),
    ]

    comparisons = evaluator.compare_strategies(candidate_plans, track_temp=track_temp)

    # Strategy Comparison Bar Chart
    st.markdown(
        """
    <div class="chart-wrap">
        <div class="chart-title">Race Time Penalty vs Fastest Candidate Strategy</div>
        <div class="chart-subtitle">
            Cumulative race time delta in seconds relative to the global fastest strategy
        </div>
    """,
        unsafe_allow_html=True,
    )
    fig_comp = plot_strategy_comparison(comparisons, is_dark=is_dark)
    st.plotly_chart(fig_comp, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    # Strategy Comparison Table
    table_rows = ""
    for idx, c in enumerate(comparisons, start=1):
        stint_badges = []
        for s in c["stints"]:
            comp_name = s["compound"]
            cls_name = f"badge-{comp_name.lower()}"
            stint_badges.append(f"<span class='badge {cls_name}'>{comp_name} ({s['laps']}L)</span>")
        stints_html = " &rarr; ".join(stint_badges)

        delta_val = c["delta_to_fastest_seconds"]
        delta_label = (
            "<span style='color: #22c55e; font-weight: 700;'>FASTEST</span>"
            if delta_val == 0.0
            else f"+{delta_val:.2f}s"
        )

        fia_badge = (
            "<span class='badge badge-low'>LEGAL</span>"
            if c["is_compliant"]
            else "<span class='badge badge-critical'>ILLEGAL</span>"
        )

        t_min = int(c["total_time_seconds"] // 60)
        t_sec = c["total_time_seconds"] % 60

        table_rows += f"""
        <tr>
            <td><strong>#{idx}</strong></td>
            <td>{c["strategy_name"]}</td>
            <td>{stints_html}</td>
            <td>{c["pit_stops"]}</td>
            <td>{t_min}m {t_sec:.1f}s</td>
            <td>{delta_label}</td>
            <td>{fia_badge}</td>
        </tr>
        """

    st.markdown(
        f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>Rank</th>
                <th>Strategy Name</th>
                <th>Stint Allocation</th>
                <th>Stops</th>
                <th>Total Race Time</th>
                <th>Delta to Fastest</th>
                <th>FIA Rules</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    """,
        unsafe_allow_html=True,
    )
