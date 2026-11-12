"""Multi-season Formula 1 historical race statistics dashboard view (2021–2026).

Provides interactive exploration of Grand Prix results, winning pit strategies,
safety car frequencies, undercut success rates, and multi-year strategy distributions.
"""

from __future__ import annotations

import streamlit as st

from stratos.dashboard.charts import plot_multi_season_strategy_distribution
from stratos.data.historical_db import (
    HISTORICAL_RACES,
    get_available_seasons,
    get_multi_season_strategy_distribution,
    get_races_for_season,
)


def render_historical_stats_view(is_dark: bool = True) -> None:
    """Render the multi-season race statistics and historical analysis view."""
    st.markdown("### 📈 Multi-Season Race Statistics & Historical Intelligence")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.25rem;'>"
        "Official race telemetry records, winning pit stop strategies, and tactical "
        "benchmarks spanning seasons 2021 through 2026."
        "</p>",
        unsafe_allow_html=True,
    )

    seasons = get_available_seasons()

    # 1. Season & Race Selection Controls
    c_season, c_race = st.columns([0.35, 0.65])

    with c_season:
        season_labels = [
            f"{s} (Championship Season)" if s == 2026 else str(s) for s in seasons
        ]
        selected_season_idx = st.selectbox(
            "Select Championship Season",
            options=range(len(seasons)),
            format_func=lambda i: season_labels[i],
            index=0,  # 2026 is default
            key="hist_season_select",
        )
        selected_season = seasons[selected_season_idx]

    races_in_season = get_races_for_season(selected_season)
    race_options = [
        f"{r.country_flag} R{r.round_num}: {r.race_name}" for r in races_in_season
    ]

    with c_race:
        selected_race_idx = st.selectbox(
            f"Select Grand Prix ({selected_season})",
            options=range(len(race_options)),
            format_func=lambda i: race_options[i],
            index=0,
            key=f"hist_race_select_{selected_season}",
        )
        selected_race = races_in_season[selected_race_idx]

    st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)

    # 2. Key Race Metrics Top Cards (Row of 4)
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Race Winner & Constructor</div>
            <div class="metric-value" style="font-size: 1.30rem;">
                {selected_race.country_flag} {selected_race.winner_driver}
                <span style="font-size: 0.80rem; color: var(--accent-cyan); font-weight: 500;">
                    ({selected_race.winner_team})
                </span>
            </div>
            <div class="metric-delta delta-cyan">
                Fastest: {selected_race.fastest_lap_driver} ({selected_race.fastest_lap_time})
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m2:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Winning Strategy</div>
            <div class="metric-value" style="font-size: 1.05rem; color: #38bdf8;">
                {selected_race.winning_strategy.split(':')[0]}
            </div>
            <div class="metric-delta delta-green">
                {selected_race.winning_strategy.split(':')[-1].strip()}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m3:
        sc_total = selected_race.safety_car_count + selected_race.vsc_count
        sc_cls = (
            "delta-red"
            if sc_total >= 2
            else ("delta-amber" if sc_total == 1 else "delta-green")
        )
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Pit Stops & Neutralizations</div>
            <div class="metric-value">
                {selected_race.total_pit_stops}
                <span style="font-size: 0.85rem; color: var(--text-muted);">stops</span>
            </div>
            <div class="metric-delta {sc_cls}">
                {selected_race.safety_car_count} SC &bull; {selected_race.vsc_count} VSC periods
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with m4:
        uc_pct = int(selected_race.undercut_success_rate * 100)
        uc_cls = "delta-green" if uc_pct >= 65 else ("delta-amber" if uc_pct >= 40 else "delta-red")
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-label">Undercut Potency & Conditions</div>
            <div class="metric-value">
                {uc_pct}%
                <span style="font-size: 0.85rem; color: var(--text-muted);">success</span>
            </div>
            <div class="metric-delta {uc_cls}">
                {selected_race.avg_track_temp:.1f}°C &bull; {selected_race.weather_condition}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)

    # 3. Two-Column Analytics Layout: Strategy Distribution vs Season Overview Table
    col_chart, col_table = st.columns([0.48, 0.52])

    with col_chart:
        st.markdown(
            """
        <div class="dashboard-card" style="height: 100%;">
            <div class="card-header-row">
                <div class="card-title">Cross-Season Strategy Trends (2021–2026)</div>
                <span class="badge badge-green">All Championship Years</span>
            </div>
            <p style="font-size: 0.76rem; color: var(--text-dim); margin-bottom: 0.5rem;">
                Historical evolution of 1-stop vs 2-stop dominance across regulations.
            </p>
        """,
            unsafe_allow_html=True,
        )
        dist_data = get_multi_season_strategy_distribution()
        fig_dist = plot_multi_season_strategy_distribution(dist_data, is_dark=is_dark)
        st.plotly_chart(fig_dist, use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)

    with col_table:
        st.markdown(
            f"""
        <div class="dashboard-card" style="height: 100%;">
            <div class="card-header-row">
                <div class="card-title">{selected_season} Grand Prix Calendar Records</div>
                <span class="badge badge-cyan">{len(races_in_season)} Races</span>
            </div>
            <table class="f1-table" style="font-size: 0.76rem;">
                <thead>
                    <tr>
                        <th>Round</th>
                        <th>Grand Prix</th>
                        <th>Winner</th>
                        <th>Strategy</th>
                        <th>Pits</th>
                        <th>SC</th>
                        <th>Track</th>
                    </tr>
                </thead>
                <tbody>
        """,
            unsafe_allow_html=True,
        )

        for r in races_in_season:
            is_active = r.round_num == selected_race.round_num
            active_style = (
                'style="background: rgba(2,132,199,0.18); font-weight: 700;"'
                if is_active
                else ""
            )
            clean_strat = r.winning_strategy.split(":")[0]
            st.markdown(
                f"""
                    <tr {active_style}>
                        <td class="mono">R{r.round_num}</td>
                        <td>{r.country_flag} {r.race_name.replace(" Grand Prix", "")}</td>
                        <td class="mono">
                            <strong>{r.winner_driver}</strong> ({r.winner_team[:3]})
                        </td>
                        <td style="color: #38bdf8;">{clean_strat}</td>
                        <td class="mono">{r.total_pit_stops}</td>
                        <td class="mono">{r.safety_car_count}</td>
                        <td class="mono">{r.avg_track_temp:.0f}°C</td>
                    </tr>
            """,
                unsafe_allow_html=True,
            )

        st.markdown(
            """
                </tbody>
            </table>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)

    # 4. Multi-Year Venue Comparison (e.g. Sakhir or selected circuit across all years)
    st.markdown(
        f"""
    <div class="dashboard-card">
        <div class="card-header-row">
            <div class="card-title">
                {selected_race.country_flag} Multi-Year Venue History: {selected_race.circuit_name}
            </div>
            <span style="font-size: 0.72rem; color: var(--text-dim);">
                Historical comparison at this venue (2021–2026)
            </span>
        </div>
        <p style="font-size: 0.76rem; color: var(--text-muted); margin-bottom: 0.75rem;">
            Tracking pit stop counts, winning tyre strategies, and safety car interventions
            at this circuit across regulations.
        </p>
        <table class="f1-table">
            <thead>
                <tr>
                    <th>Season</th>
                    <th>Grand Prix</th>
                    <th>Winner</th>
                    <th>Winning Strategy</th>
                    <th>Total Pits</th>
                    <th>Safety Cars</th>
                    <th>Fastest Lap</th>
                    <th>Pit Loss Delta</th>
                    <th>Undercut %</th>
                </tr>
            </thead>
            <tbody>
    """,
        unsafe_allow_html=True,
    )

    venue_name_part = selected_race.circuit_name.split("(")[0].strip()
    matching_venue_races = [
        r
        for r in HISTORICAL_RACES
        if venue_name_part.lower() in r.circuit_name.lower()
        or selected_race.race_name.lower() in r.race_name.lower()
    ]
    matching_venue_races.sort(key=lambda r: r.season, reverse=True)

    for vr in matching_venue_races:
        is_highlight = vr.season == selected_season
        h_style = (
            'class="highlight-stratos"'
            if is_highlight
            else ""
        )
        season_badge = (
            f"<span class='badge badge-cyan'>{vr.season}</span>"
            if vr.season == 2026
            else f"<strong>{vr.season}</strong>"
        )
        st.markdown(
            f"""
                <tr {h_style}>
                    <td class="mono">{season_badge}</td>
                    <td>{vr.country_flag} {vr.race_name}</td>
                    <td class="mono"><strong>{vr.winner_driver}</strong> ({vr.winner_team})</td>
                    <td style="color: #38bdf8;">{vr.winning_strategy}</td>
                    <td class="mono">{vr.total_pit_stops}</td>
                    <td class="mono">{vr.safety_car_count} SC, {vr.vsc_count} VSC</td>
                    <td class="mono">{vr.fastest_lap_driver} ({vr.fastest_lap_time})</td>
                    <td class="mono">+{vr.avg_pit_loss:.1f}s</td>
                    <td class="mono">{int(vr.undercut_success_rate * 100)}%</td>
                </tr>
        """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
            </tbody>
        </table>
    </div>
    """,
        unsafe_allow_html=True,
    )
