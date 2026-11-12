"""Next Race Predictive Intelligence and Explainability view for BWT Alpine F1 Team."""

from __future__ import annotations

import datetime
import json
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from stratos.explainability.explainer import PredictionExplainer
from stratos.models.interactive_engine import (
    EngineerInputState,
    InteractiveEngineerEngine,
)
from stratos.models.pit import TrackStatus
from stratos.models.tyre import TyreCompound
from stratos.prediction.features import PREDICTION_STAGES, FeatureExtractor
from stratos.prediction.models import StratosRaceForecaster
from stratos.prediction.schedule import NextEventDetector
from stratos.storage.database import StratosDB


def render_next_race_view(db: StratosDB | None = None, is_dark: bool = True) -> None:
    """Render next race forecasting, engineer telemetry inputs, and strategy discussions."""
    if db is None:
        db = StratosDB()
    st.markdown("### 🔮 BWT Alpine Next Grand Prix Predictive Intelligence")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.88rem; margin-bottom: 1.25rem;'>"
        "Dual predictive intelligence cockpit: statistical machine learning forecasting "
        "across 4 temporal stages, and live race-engineer telemetry injection with real-time "
        "multi-agent strategy debates."
        "</p>",
        unsafe_allow_html=True,
    )

    events = db.get_events()
    if not events:
        st.info("No race events loaded in database. Import sessions from History & Data.")
        return

    detector = NextEventDetector(db=db)
    detected_next = detector.get_next_event()

    tab_forecast, tab_telemetry = st.tabs(
        [
            "🔮 Grand Prix Forecaster & Explainability",
            "💬 Live Engineer Telemetry & Strategy Discussions",
        ]
    )

    with tab_forecast:
        _render_forecast_tab(db=db, events=events, detected_next=detected_next)

    with tab_telemetry:
        _render_telemetry_discussion_tab(db=db, events=events)


def _render_forecast_tab(
    db: StratosDB, events: list[dict[str, Any]], detected_next: Any
) -> None:
    """Render the statistical machine-learning prediction & explainability engine."""
    col_ev, col_stg, col_drv = st.columns([1.3, 1.2, 0.9])

    event_names = [f"{e['season']} - {e['event_name']} (R{e['round_number']})" for e in events]
    default_idx = 0
    for idx, e in enumerate(events):
        if (
            e["season"] == detected_next.season
            and e["round_number"] == detected_next.round_number
        ):
            default_idx = idx
            break

    with col_ev:
        selected_event_str = st.selectbox(
            "Target Grand Prix Event",
            options=event_names,
            index=default_idx,
            key="fc_event",
        )
        selected_event = events[event_names.index(selected_event_str)]

    with col_stg:
        selected_stage = st.radio(
            "Prediction Stage (Temporal Cutoff)",
            options=PREDICTION_STAGES,
            index=0,
            horizontal=True,
            key="fc_stage",
        )

    with col_drv:
        selected_driver = st.selectbox(
            "Alpine Driver",
            options=["GAS", "OCO", "DOO"],
            format_func=lambda x: {
                "GAS": "Pierre Gasly (#10)",
                "OCO": "Esteban Ocon (#31)",
                "DOO": "Jack Doohan (#61)",
            }.get(x, x),
            key="fc_driver",
        )

    with st.expander("🛠️ Engineering Assumptions & Interactive Overrides", expanded=False):
        ca1, ca2, ca3, ca4 = st.columns(4)
        with ca1:
            override_grid = st.number_input(
                "Starting Grid Position Override",
                min_value=1,
                max_value=20,
                value=10 if selected_stage in ("POST_QUALIFYING", "PRE_RACE") else 11,
                key="fc_override_grid",
            )
        with ca2:
            override_track_temp = st.slider(
                "Track Surface Temperature (°C)",
                min_value=15.0,
                max_value=55.0,
                value=32.0,
                step=1.0,
                key="fc_override_temp",
            )
        with ca3:
            override_rain_prob = st.slider(
                "Precipitation Probability",
                min_value=0.0,
                max_value=1.0,
                value=0.0,
                step=0.05,
                key="fc_override_rain",
            )
        with ca4:
            override_practice_pace = st.number_input(
                "Practice Pace Deficit (%)",
                min_value=0.0,
                max_value=5.0,
                value=1.15,
                step=0.05,
                key="fc_override_pace",
            )

    extractor = FeatureExtractor(db=db)
    feature_vec = extractor.extract_features(
        season=selected_event["season"],
        round_number=selected_event["round_number"],
        stage=selected_stage,
        driver_code=selected_driver,
        event_name=selected_event["event_name"],
    )

    feature_vec.features["qualifying_grid_pos"] = float(override_grid)
    feature_vec.features["grid_position"] = float(override_grid)
    feature_vec.features["weather_rain_prob"] = float(override_rain_prob)
    if selected_stage != "PRE_WEEKEND":
        feature_vec.features["practice_pace_delta"] = float(override_practice_pace)

    forecaster = StratosRaceForecaster()
    report = forecaster.forecast(
        feature_vec,
        prediction_cutoff=f"{selected_stage} Cutoff",
        assumptions=(
            f"Assumed Track Temp: {override_track_temp}°C, Rain Prob: {override_rain_prob:.2f}. "
            f"Stage: {selected_stage}."
        ),
    )

    explainer = PredictionExplainer(db=db)
    explanation = explainer.explain_forecast(
        report,
        event_name=selected_event["event_name"],
        circuit_name=selected_event.get("location", "Grand Prix Circuit"),
    )

    col_btn, col_msg = st.columns([1.3, 3.0])
    with col_btn:
        if st.button("⚡ Generate & Save Official Forecast", type="primary", key="btn_save_fc"):
            pred_ids = report.save(db)
            st.session_state["last_saved_preds"] = pred_ids
            st.success(f"Saved {len(pred_ids)} forecast records to stratos.db!")

    with col_msg:
        if "last_saved_preds" in st.session_state:
            st.caption(
                f"✅ Latest Forecast IDs: `{', '.join(st.session_state['last_saved_preds'])}` "
                f"| Cutoff: `{report.prediction_cutoff}`"
            )

    st.markdown("<div style='height: 0.6rem;'></div>", unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    f_low, f_high = report.finish_position_interval
    q_low, q_high = report.qualifying_interval

    with k1:
        st.markdown(
            f"""
            <div class="dashboard-card" style="padding: 1rem; border-left: 4px solid #38bdf8;">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Expected Finish Position
                </div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #38bdf8; margin-top: 4px;">
                    P{report.expected_finish_position:.1f}
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    90% Interval: <b>P{f_low:.0f} to P{f_high:.0f}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k2:
        pod_pct = report.podium_probability * 100
        top6_pct = report.top_6_probability * 100
        st.markdown(
            f"""
            <div class="dashboard-card" style="padding: 1rem; border-left: 4px solid #10b981;">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Points Probability (P1–P10)
                </div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #10b981; margin-top: 4px;">
                    {report.points_probability * 100:.1f}%
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    Podium: <b>{pod_pct:.1f}%</b> &bull; Top 6: <b>{top6_pct:.1f}%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k3:
        st.markdown(
            f"""
            <div class="dashboard-card" style="padding: 1rem; border-left: 4px solid #0284c7;">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Qualifying Pace Deficit
                </div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #0284c7; margin-top: 4px;">
                    +{report.qualifying_pace_delta_pct:.2f}%
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    90% Interval: <b>+{q_low:.2f}% to +{q_high:.2f}%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k4:
        diff = report.expected_finish_position - report.baseline_predicted_finish
        diff_str = f"{diff:+.1f} vs Rolling" if abs(diff) > 0.05 else "Matches Baseline"
        st.markdown(
            f"""
            <div class="dashboard-card" style="padding: 1rem; border-left: 4px solid #f59e0b;">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Rolling Pace Baseline
                </div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #f59e0b; margin-top: 4px;">
                    P{report.baseline_predicted_finish:.1f}
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    Forecaster Delta: <b>{diff_str}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.markdown("#### 📊 Calibrated Finishing Position Probability Distribution")

    pos_labels = [f"P{i}" for i in range(1, 21)]
    pos_probs = [report.position_distribution.get(p, 0.0) * 100 for p in pos_labels]

    bar_colors = [
        "#10b981" if i < 3 else "#38bdf8" if i < 10 else "rgba(148, 163, 184, 0.35)"
        for i in range(20)
    ]

    fig_dist = go.Figure(
        go.Bar(
            x=pos_labels,
            y=pos_probs,
            marker=dict(color=bar_colors),
            text=[f"{p:.1f}%" if p >= 2.0 else "" for p in pos_probs],
            textposition="outside",
        )
    )

    fig_dist.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17, 27, 46, 0.6)",
        height=280,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis=dict(
            title="Classified Finishing Position",
            gridcolor="rgba(255,255,255,0.06)",
            tickfont=dict(color="#94a3b8"),
        ),
        yaxis=dict(
            title="Probability (%)",
            gridcolor="rgba(255,255,255,0.06)",
            tickfont=dict(color="#94a3b8"),
            range=[0, max(pos_probs) * 1.25],
        ),
    )
    st.plotly_chart(fig_dist, use_container_width=True)

    st.markdown("#### 🔬 Engineering Explainability & Measurable Feature Attribution")
    st.markdown(
        f"""
        <div style="background: rgba(17, 27, 46, 0.6); border: 1px solid var(--border);
                    border-radius: 8px; padding: 0.9rem; margin-bottom: 1rem; font-size: 0.90rem;">
            <b>Strategic Assessment:</b> {explanation.headline}
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_imp, c_drv = st.columns([1.6, 1.2])

    with c_imp:
        st.markdown("##### 📐 Measurable Feature Attribution")
        impact_table = [
            {
                "Feature": imp.display_name,
                "Value": round(imp.feature_value, 3),
                "Impact (Pos)": f"{imp.impact_positions:+.2f}",
                "Status": (
                    "🟢 Favorable"
                    if imp.direction == "FAVORABLE"
                    else "🔴 Unfavorable"
                    if imp.direction == "UNFAVORABLE"
                    else "⚪ Neutral"
                ),
                "Rationale": imp.explanation,
            }
            for imp in explanation.feature_impacts
        ]
        st.dataframe(impact_table, use_container_width=True, hide_index=True)

    with c_drv:
        st.markdown("##### ⚡ Key Operational Drivers")
        if explanation.positive_drivers:
            st.markdown("**Performance Boosters:**")
            for p in explanation.positive_drivers:
                st.markdown(
                    f"- ✅ <span style='color:#10b981;'>{p}</span>",
                    unsafe_allow_html=True,
                )
        if explanation.negative_drivers:
            st.markdown("**Performance Inhibitors:**")
            for n in explanation.negative_drivers:
                st.markdown(
                    f"- ⚠️ <span style='color:#ef4444;'>{n}</span>",
                    unsafe_allow_html=True,
                )
        if explanation.uncertainty_factors:
            st.markdown("**Uncertainty Drivers:**")
            for u in explanation.uncertainty_factors:
                st.markdown(
                    f"- 🔍 <span style='color:#94a3b8;'>{u}</span>",
                    unsafe_allow_html=True,
                )

    st.markdown("##### ⚔️ Midfield Competitors in Alpine's Finishing Window")
    rival_rows = [
        {
            "Competitor": r.constructor_name,
            "Pace Deficit": f"+{r.recent_pace_delta_pct:.2f}%",
            "Recent Avg Finish": f"P{r.recent_avg_finish:.1f}",
            "Status": (
                "🟢 Alpine Ahead"
                if r.head_to_head_status == "AHEAD"
                else "🔴 Rival Ahead"
                if r.head_to_head_status == "BEHIND"
                else "⚔️ Direct Contest"
            ),
            "Engineering Context": r.comparison_summary,
        }
        for r in explanation.rival_benchmarks
    ]
    st.dataframe(rival_rows, use_container_width=True, hide_index=True)

    col_hist, col_tech = st.columns(2)
    with col_hist:
        st.markdown("##### 🏛️ Relevant Historical Precedents")
        for a in explanation.historical_analogues:
            st.markdown(
                f"""
                <div style="background: rgba(17, 27, 46, 0.4); border-left: 3px solid #0284c7;
                            padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; font-size: 0.82rem;">
                    <b>{a.season} {a.event_name}</b> ({a.circuit_name})<br/>
                    Start: <b>{a.starting_position}</b> &bull;
                    Finish: <b>{a.finishing_position}</b> ({a.points} pts)<br/>
                    <span style="color: var(--text-muted);">{a.context_note}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_tech:
        st.markdown("##### 🏎️ Enstone & Viry Operational Notes")
        st.markdown(
            f"""
            <div style="background: rgba(17, 27, 46, 0.4); border-left: 3px solid #38bdf8;
                        padding: 0.6rem 0.8rem; font-size: 0.82rem; line-height: 1.5;">
                {explanation.technical_context.replace(chr(10), '<br/>')}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    cd1, cd2 = st.columns([1.5, 3.5])
    with cd1:
        md_report = explanation.to_markdown()
        st.download_button(
            label="📄 Download Full Prediction Report (.md)",
            data=md_report,
            file_name=f"stratos_forecast_{selected_event['season']}_r{selected_event['round_number']}.md",
            mime="text/markdown",
            key="dl_md_fc",
        )
    with cd2:
        json_report = json.dumps(explanation.to_dict(), indent=2)
        st.download_button(
            label="💾 Download Structured Forecast JSON",
            data=json_report,
            file_name=f"stratos_forecast_{selected_event['season']}_r{selected_event['round_number']}.json",
            mime="application/json",
            key="dl_json_fc",
        )


def _render_telemetry_discussion_tab(
    db: StratosDB | None = None,
    events: list[dict[str, Any]] | None = None,
) -> None:
    """Render the live engineer telemetry input panel and multi-agent discussion engine."""
    st.markdown("#### 💬 Pit-Wall Telemetry Injection & Multi-Agent Deliberations")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.86rem; margin-bottom: 1rem;'>"
        "Inject live telemetry parameters into the strategy core to trigger instant multi-stint "
        "predictions, traffic wake projections, and conversational multi-agent debate transcripts."
        "</p>",
        unsafe_allow_html=True,
    )

    col_t1, col_t2, col_t3 = st.columns(3)

    with col_t1:
        st.markdown("##### 📍 Circuit & Environmental Conditions")
        circuit_choice = st.selectbox(
            "Circuit Profile",
            options=["bahrain", "silverstone", "monaco", "spa", "monza", "suzuka"],
            index=0,
            format_func=lambda x: {
                "bahrain": "Bahrain International Circuit (Sakhir)",
                "silverstone": "Silverstone Circuit (UK)",
                "monaco": "Circuit de Monaco (Monte Carlo)",
                "spa": "Circuit de Spa-Francorchamps (Belgium)",
                "monza": "Autodromo Nazionale Monza (Italy)",
                "suzuka": "Suzuka International Racing Course (Japan)",
            }.get(x, x.title()),
            key="eng_circuit",
        )
        total_laps_map = {
            "bahrain": 57,
            "silverstone": 52,
            "monaco": 78,
            "spa": 44,
            "monza": 53,
            "suzuka": 53,
        }
        total_laps_val = total_laps_map.get(circuit_choice, 57)
        current_lap_val = st.slider(
            "Current Race Lap",
            min_value=1,
            max_value=total_laps_val,
            value=min(22, total_laps_val),
            key="eng_lap",
        )
        track_status_str = st.selectbox(
            "Track Neutralization State",
            options=["GREEN", "VSC", "SAFETY_CAR", "RED_FLAG"],
            index=0,
            key="eng_status",
        )
        track_temp_val = st.slider(
            "Track Surface Temperature (°C)",
            min_value=15.0,
            max_value=55.0,
            value=32.0,
            step=1.0,
            key="eng_temp",
        )
        rain_val = st.slider(
            "Current Rainfall Rate (mm/h)",
            min_value=0.0,
            max_value=10.0,
            value=0.0,
            step=0.1,
            key="eng_rain",
        )
        rain_fc_val = st.slider(
            "Rain Arrival Forecast (Laps)",
            min_value=0,
            max_value=15,
            value=0,
            help="0 indicates dry radar for the short-term window",
            key="eng_rain_fc",
        )

    with col_t2:
        st.markdown("##### 🏎️ Alpine Car & Tyre Stint Telemetry")
        driver_choice = st.selectbox(
            "Target Alpine Driver",
            options=["GAS", "OCO", "DOO"],
            format_func=lambda x: {
                "GAS": "Pierre Gasly (#10)",
                "OCO": "Esteban Ocon (#31)",
                "DOO": "Jack Doohan (#61)",
            }.get(x, x),
            key="eng_driver",
        )
        cur_pos_val = st.slider(
            "Current Track Position",
            min_value=1,
            max_value=20,
            value=4,
            key="eng_pos",
        )
        gap_lead_val = st.number_input(
            "Interval to Race Leader (s)",
            min_value=0.0,
            max_value=90.0,
            value=1.24,
            step=0.1,
            key="eng_gap_lead",
        )
        gap_ahead_val = st.number_input(
            "Interval to Car Ahead (s)",
            min_value=0.0,
            max_value=30.0,
            value=0.85,
            step=0.05,
            key="eng_gap_ahead",
        )
        cur_comp_str = st.selectbox(
            "Current Fitted Tyre Compound",
            options=["MEDIUM", "HARD", "SOFT", "INTERMEDIATE", "WET"],
            index=0,
            key="eng_compound",
        )
        stint_age_val = st.number_input(
            "Stint Age (Laps Completed)",
            min_value=1,
            max_value=total_laps_val,
            value=20,
            key="eng_age",
        )
        tyre_wear_val = st.slider(
            "Estimated Remaining Grip (%)",
            min_value=0,
            max_value=100,
            value=68,
            key="eng_grip",
        )
        hard_sets_val = st.number_input(
            "Available Fresh Hard Sets",
            min_value=0,
            max_value=4,
            value=2,
            key="eng_hard_sets",
        )

    with col_t3:
        st.markdown("##### ⚔️ Key Tactical Rival")
        rival_code = st.selectbox(
            "Key Tactical Competitor",
            options=["VER", "NOR", "LEC", "HAM", "PIA", "RUS", "SAI", "HUL", "ALB", "TSU"],
            index=0,
            key="eng_rival",
        )
        rival_gap_val = st.number_input(
            "Interval to Rival (s)",
            min_value=0.0,
            max_value=40.0,
            value=1.24,
            step=0.1,
            key="eng_rival_gap",
        )
        rival_comp_str = st.selectbox(
            "Rival Fitted Compound",
            options=["MEDIUM", "HARD", "SOFT", "INTERMEDIATE"],
            index=0,
            key="eng_rival_comp",
        )
        rival_age_val = st.number_input(
            "Rival Stint Age (Laps)",
            min_value=1,
            max_value=total_laps_val,
            value=20,
            key="eng_rival_age",
        )
        rival_action_str = st.selectbox(
            "Rival Stint Status",
            options=["staying_out", "boxed_now", "box_imminent"],
            index=0,
            format_func=lambda x: {
                "staying_out": "Staying Out on Circuit",
                "boxed_now": "🚨 BOXED THIS LAP (In Pit Lane)",
                "box_imminent": "Pit Crew Alerted (Box Imminent)",
            }.get(x, x),
            key="eng_rival_act",
        )

    status_map = {
        "GREEN": TrackStatus.GREEN,
        "VSC": TrackStatus.VSC,
        "SAFETY_CAR": TrackStatus.SAFETY_CAR,
        "RED_FLAG": TrackStatus.RED_FLAG,
    }
    compound_map = {
        "SOFT": TyreCompound.SOFT,
        "MEDIUM": TyreCompound.MEDIUM,
        "HARD": TyreCompound.HARD,
        "INTERMEDIATE": TyreCompound.INTERMEDIATE,
        "WET": TyreCompound.WET,
    }

    input_state = EngineerInputState(
        circuit_key=circuit_choice,
        current_lap=current_lap_val,
        total_laps=total_laps_val,
        track_status=status_map[track_status_str],
        track_temp=track_temp_val,
        rainfall=rain_val,
        rain_forecast_laps=rain_fc_val,
        target_driver=driver_choice,
        current_position=cur_pos_val,
        gap_to_leader=gap_lead_val,
        gap_to_car_ahead=gap_ahead_val,
        current_compound=compound_map[cur_comp_str],
        tyre_age=stint_age_val,
        tyre_wear_pct=tyre_wear_val,
        rival_driver=rival_code,
        rival_gap=rival_gap_val,
        rival_compound=compound_map[rival_comp_str],
        rival_tyre_age=rival_age_val,
        rival_action=rival_action_str,
        fresh_hard_sets=hard_sets_val,
    )

    eng_engine = InteractiveEngineerEngine()
    eng_res = eng_engine.evaluate_engineer_inputs(input_state)

    st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)

    # 1. Live Radio Transmission Callout Banner
    bg_gradient = (
        "background: linear-gradient(90deg, rgba(2, 132, 199, 0.25), rgba(236, 72, 153, 0.25));"
    )
    st.markdown(
        f"""
        <div style="{bg_gradient} border: 1px solid #38bdf8; border-radius: 8px;
                    padding: 1rem; margin-bottom: 1.25rem;">
            <div style="font-size: 0.72rem; text-transform: uppercase; color: #38bdf8;
                        font-weight: 700; letter-spacing: 0.08em; margin-bottom: 0.4rem;">
                📻 LIVE PIT-WALL RADIO DIRECTIVE TRANSMISSION
            </div>
            <div style="font-size: 1.05rem; font-family: monospace;
                        font-weight: 700; color: #f8fafc;">
                "{eng_res.radio_transmission}"
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. Key Telemetry Predictive Indicators
    r1, r2, r3, r4 = st.columns(4)

    with r1:
        st.markdown(
            f"""
            <div class="dashboard-card" style="padding: 1rem; border-left: 4px solid #10b981;">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Optimal Pit Stop Window
                </div>
                <div style="font-size: 1.45rem; font-weight: 700; color: #10b981; margin-top: 4px;">
                    Lap {eng_res.optimal_pit_lap}
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    Window: <b>L{eng_res.pit_window_range[0]} – L{eng_res.pit_window_range[1]}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r2:
        comp_color = (
            "#06b6d4"
            if eng_res.recommended_compound == TyreCompound.INTERMEDIATE
            else "#f8fafc"
            if eng_res.recommended_compound == TyreCompound.HARD
            else "#eab308"
        )
        st.markdown(
            f"""
            <div class="dashboard-card" style="padding: 1rem; border-left: 4px solid #38bdf8;">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Recommended Tyre
                </div>
                <div style="font-size: 1.45rem; font-weight: 700; color: {comp_color};
                            margin-top: 4px;">
                    {eng_res.recommended_compound.value}
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    Plan: <b>{eng_res.plan_name}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r3:
        corridor_color = "#ef4444" if eng_res.traffic_risk_flag else "#10b981"
        corridor_text = "⚠️ Traffic Trap" if eng_res.traffic_risk_flag else "Clear Corridor"
        st.markdown(
            f"""
            <div class="dashboard-card"
                 style="padding: 1rem; border-left: 4px solid {corridor_color};">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Projected Rejoin Corridor
                </div>
                <div style="font-size: 1.45rem; font-weight: 700; color: {corridor_color};
                            margin-top: 4px;">
                    P{eng_res.rejoin_position}
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    Status: <b>{corridor_text}</b> (+{eng_res.rejoin_gap:.1f}s)
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r4:
        st.markdown(
            f"""
            <div class="dashboard-card" style="padding: 1rem; border-left: 4px solid #f59e0b;">
                <div style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase;">
                    Undercut Potency Advantage
                </div>
                <div style="font-size: 1.45rem; font-weight: 700; color: #f59e0b; margin-top: 4px;">
                    +{eng_res.undercut_potency_seconds:.2f}s
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                    Podium: <b>{eng_res.podium_probability_pct}%</b> &bull;
                    Win: <b>{eng_res.win_probability_pct}%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # 3. Strategy Alternatives Benchmark Table
    st.markdown("##### 📋 Multi-Stint Strategic Alternatives Benchmark")
    alt_table = [
        {
            "Strategic Plan": a["plan"],
            "Stops": a["stops"],
            "Stint Sequence": a["compounds"],
            "Estimated Race Time": a["est_time"],
            "Pace Delta": a["delta"],
            "Traffic / Risk Penalty": a["risk"],
        }
        for a in eng_res.strategy_alternatives
    ]
    st.dataframe(alt_table, use_container_width=True, hide_index=True)

    st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)

    # 4. Multi-Agent Discussion Transcript
    st.markdown("##### 🎙️ Pit-Wall Multi-Agent Deliberation Transcript")
    for msg in eng_res.dialogue_thread:
        st.markdown(
            f"""
            <div style="background: rgba(17, 27, 46, 0.7); border: 1px solid var(--border);
                        border-left: 4px solid {msg.color_hex}; border-radius: 8px;
                        padding: 0.9rem 1.1rem; margin-bottom: 0.75rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;
                            margin-bottom: 0.4rem;">
                    <div>
                        <span style="font-size: 1.1rem; margin-right: 0.35rem;">
                            {msg.avatar_emoji}
                        </span>
                        <span style="font-weight: 700; color: #f8fafc; font-size: 0.92rem;">
                            {msg.agent_name}
                        </span>
                        <span style="color: var(--text-dim); font-size: 0.78rem;
                                     margin-left: 0.4rem;">
                            ({msg.agent_role})
                        </span>
                    </div>
                    <span style="background: rgba(255,255,255,0.08); padding: 2px 8px;
                                 border-radius: 12px; font-size: 0.74rem; color: #94a3b8;">
                        Confidence: <b>{int(msg.confidence * 100)}%</b>
                    </span>
                </div>
                <div style="font-size: 0.86rem; color: #cbd5e1; line-height: 1.45;
                            margin-bottom: 0.5rem;">
                    {msg.dialogue_text}
                </div>
                <div style="background: rgba(0,0,0,0.25); border-left: 2px solid {msg.color_hex};
                            padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.76rem;
                            font-weight: 600; color: {msg.color_hex};">
                    ⚡ {msg.directive_callout}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 5. Pit-Wall Decision Archival & Export
    st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)
    st.markdown("##### 💾 Pit-Wall Decision Archival & Export")
    col_act1, col_act2 = st.columns([1, 1])

    export_payload = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "circuit": circuit_choice,
        "target_driver": driver_choice,
        "current_lap": current_lap_val,
        "total_laps": total_laps_val,
        "track_status": track_status_str,
        "fitted_compound": cur_comp_str,
        "optimal_pit_lap": eng_res.optimal_pit_lap,
        "pit_window_range": list(eng_res.pit_window_range),
        "recommended_compound": eng_res.recommended_compound.value,
        "plan_name": eng_res.plan_name,
        "radio_transmission": eng_res.radio_transmission,
        "win_probability_pct": eng_res.win_probability_pct,
        "podium_probability_pct": eng_res.podium_probability_pct,
        "strategy_confidence_pct": eng_res.strategy_confidence_pct,
        "rejoin_position": eng_res.rejoin_position,
        "rejoin_gap": eng_res.rejoin_gap,
        "undercut_potency_seconds": eng_res.undercut_potency_seconds,
        "alternatives": eng_res.strategy_alternatives,
        "deliberation_thread": [
            {
                "agent_id": m.agent_id,
                "agent_name": m.agent_name,
                "agent_role": m.agent_role,
                "confidence": m.confidence,
                "dialogue_text": m.dialogue_text,
                "directive_callout": m.directive_callout,
            }
            for m in eng_res.dialogue_thread
        ],
    }

    with col_act1:
        if st.button("💾 Log Decision to Strategy Ledger", key="btn_save_engineer_decision"):
            if db is not None:
                target_ev = events[0] if events else {
                    "id": f"event_{circuit_choice}_2026",
                    "season": 2026,
                    "round_number": 1,
                }
                now_ts = int(datetime.datetime.now().timestamp())
                pred_record = {
                    "id": f"eng_strat_{circuit_choice}_L{current_lap_val}_{now_ts}",
                    "prediction_cutoff": datetime.datetime.now(datetime.UTC).isoformat(),
                    "stage": f"IN_RACE_L{current_lap_val}",
                    "target_event_id": target_ev.get("id", f"ev_{circuit_choice}"),
                    "target_season": int(target_ev.get("season", 2026)),
                    "target_round": int(target_ev.get("round_number", 1)),
                    "model_version": "STRATOS-ENGINEER-v2.6",
                    "target_type": "ENGINEER_STRATEGY_DECISION",
                    "predicted_value": float(eng_res.optimal_pit_lap),
                    "interval_low": float(eng_res.pit_window_range[0]),
                    "interval_high": float(eng_res.pit_window_range[1]),
                    "distribution_json": json.dumps(export_payload),
                    "feature_values_json": json.dumps({
                        "circuit": circuit_choice,
                        "lap": current_lap_val,
                        "tyre_age": stint_age_val,
                        "grip_pct": tyre_wear_val,
                        "rival": rival_code,
                        "rival_gap": rival_gap_val,
                        "rival_action": rival_action_str,
                    }),
                    "assumptions": (
                        f"Driver {driver_choice} | L{current_lap_val}/{total_laps_val} | "
                        f"{track_status_str} | Radio: {eng_res.radio_transmission}"
                    ),
                }
                pred_id = db.save_prediction(pred_record)
                st.success(f"Strategy directive & dialogue archived in DB! ID: `{pred_id}`")
            else:
                st.info("Database instance not attached. Strategy logged to memory.")

    with col_act2:
        st.download_button(
            label="📥 Export Deliberation Transcript (JSON)",
            data=json.dumps(export_payload, indent=2),
            file_name=f"alpine_strategy_L{current_lap_val}_{circuit_choice}.json",
            mime="application/json",
            key="btn_export_engineer_transcript",
        )
