"""STRATOS: BWT Alpine Formula One Team Race Intelligence System.

Research-quality Formula 1 historical analysis and next-race prediction cockpit
with strictly four primary navigation sections:
1. OVERVIEW
2. TEAM ANALYSIS
3. NEXT RACE
4. HISTORY & DATA
"""

from __future__ import annotations

import streamlit as st

from stratos.dashboard.styles import get_css
from stratos.dashboard.views import (
    render_history_data_view,
    render_next_race_view,
    render_overview_view,
    render_team_analysis_view,
)
from stratos.prediction.schedule import NextEventDetector
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore
from stratos.storage.sample_data import seed_database_with_f1_history

st.set_page_config(
    page_title="STRATOS | Alpine F1 Race Intelligence",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_db_and_store() -> tuple[StratosDB, ParquetStore]:
    """Provide cached singletons for relational database and parquet storage."""
    if "stratos_db" not in st.session_state:
        st.session_state["stratos_db"] = StratosDB()
    if "stratos_store" not in st.session_state:
        st.session_state["stratos_store"] = ParquetStore()
    return st.session_state["stratos_db"], st.session_state["stratos_store"]


def render_sidebar(db: StratosDB, store: ParquetStore) -> str:
    """Render the functional left navigation sidebar."""
    with st.sidebar:
        # 1. Brand Logo
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-icon" style="color: #38bdf8;">▲</div>
                <div>
                    <div class="sidebar-brand-title">STRATOS</div>
                    <div class="sidebar-brand-sub">BWT ALPINE F1 INTELLIGENCE</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

        # 2. Four Primary Navigation Sections
        st.markdown(
            "<div style='font-size: 0.72rem; font-weight: 700; color: var(--text-dim); "
            "text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;'>"
            "Cockpit Navigation</div>",
            unsafe_allow_html=True,
        )

        nav_section = st.radio(
            "Navigation Menu",
            options=["OVERVIEW", "TEAM ANALYSIS", "NEXT RACE", "HISTORY & DATA"],
            index=0,
            label_visibility="collapsed",
        )

        st.markdown("---")

        # 3. System & Database Status
        events = db.get_events()
        sessions = db.get_sessions()

        st.markdown(
            "<div style='font-size: 0.72rem; font-weight: 700; color: var(--text-dim); "
            "text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;'>"
            "Relational Storage</div>",
            unsafe_allow_html=True,
        )

        if not events:
            st.warning("⚠️ Database Empty")
            if st.button("📥 Load Initial Data", use_container_width=True):
                with st.spinner("Seeding database..."):
                    cnt = seed_database_with_f1_history(db, store)
                    st.success(f"Loaded {cnt} historical results!")
                    st.rerun()
        else:
            st.markdown(
                f"""
                <div style="font-size: 0.80rem; color: var(--text-muted); line-height: 1.5;">
                    &bull; Database: <code>stratos.db</code><br/>
                    &bull; Events: <b>{len(events)} Grand Prix</b><br/>
                    &bull; Sessions: <b>{len(sessions)} Records</b><br/>
                    &bull; Parquet Store: <code>data/processed/</code>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # 4. Settings & Theme
        st.markdown(
            "<div style='font-size: 0.72rem; font-weight: 700; color: var(--text-dim); "
            "text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;'>"
            "Display Theme</div>",
            unsafe_allow_html=True,
        )
        is_dark = st.toggle("Dark Cockpit Mode", value=st.session_state.get("is_dark", True))
        st.session_state["is_dark"] = is_dark

        # 5. Footer Branding
        st.markdown(
            """
            <div style="margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border);
                        font-size: 0.70rem; color: var(--text-dim); line-height: 1.4;">
                <div style="font-weight: 700; color: #f8fafc; letter-spacing: 0.05em;">
                    STRATOS v2.0
                </div>
                <div>BWT Alpine F1 Research Intelligence.</div>
                <div style="margin-top: 2px;">Offline & FastF1 Hybrid Pipeline.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return nav_section


def main() -> None:
    """Run the main STRATOS dashboard application."""
    db, store = get_db_and_store()

    if "is_dark" not in st.session_state:
        st.session_state["is_dark"] = True

    is_dark = st.session_state["is_dark"]

    # Inject custom stylesheet
    st.markdown(get_css(is_dark=is_dark), unsafe_allow_html=True)

    # Render Functional Sidebar Navigation
    nav_section = render_sidebar(db, store)

    # Automatic Next Event Discovery for Header
    detector = NextEventDetector(db=db)
    next_event = detector.get_next_event()

    # Top Header Telemetry Bar
    st.markdown(
        f"""
        <div class="top-header">
            <div class="event-info">
                <div class="event-flag">🏎️</div>
                <div>
                    <div class="event-title">
                        BWT Alpine F1 Team &bull; {next_event.event_name}
                    </div>
                    <div class="event-subtitle">
                        Round {next_event.round_number} &bull; Season {next_event.season} &bull;
                        Enstone & Viry-Châtillon Operational Intelligence
                    </div>
                </div>
            </div>
            <div class="telemetry-pills">
                <div class="telemetry-pill-item">
                    <span>Active Section</span>
                    <span class="telemetry-pill-val">{nav_section}</span>
                </div>
                <div class="telemetry-pill-item">
                    <span>Focus Team</span>
                    <span class="telemetry-pill-val" style="color: #38bdf8;">BWT Alpine F1</span>
                </div>
                <div class="telemetry-pill-item">
                    <span>Engine</span>
                    <span class="telemetry-pill-val">Renault E-Tech</span>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.6rem;">
                <span class="badge badge-green" style="padding: 0.35rem 0.65rem;">
                    ● Active Intelligence
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # Render Selected Primary Navigation Section
    # -------------------------------------------------------------------------
    if nav_section == "OVERVIEW":
        render_overview_view(db=db, is_dark=is_dark)

    elif nav_section == "TEAM ANALYSIS":
        render_team_analysis_view(db=db, is_dark=is_dark)

    elif nav_section == "NEXT RACE":
        render_next_race_view(db=db, is_dark=is_dark)

    elif nav_section == "HISTORY & DATA":
        render_history_data_view(db=db, store=store, is_dark=is_dark)


if __name__ == "__main__":
    main()
