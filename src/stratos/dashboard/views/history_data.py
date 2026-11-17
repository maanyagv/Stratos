"""History & Data cockpit for STRATOS data ingestion, provenance, and evaluation."""

from __future__ import annotations

import datetime
from pathlib import Path

import streamlit as st

from stratos.explainability.explainer import PredictionEvaluator
from stratos.ingestion.pipeline import IngestionPipeline
from stratos.prediction.backtesting import ChronologicalBacktester
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore
from stratos.storage.sample_data import seed_database_with_f1_history


def render_history_data_view(
    db: StratosDB | None = None,
    store: ParquetStore | None = None,
    is_dark: bool = True,
) -> None:
    """Render data management, ingestion, provenance, and model evaluation cockpit."""
    if db is None:
        db = StratosDB()
    st.markdown("### 💾 Formula 1 Historical Archive, Data Provenance & Model Verification")
    st.markdown(
        "<p style='color: var(--text-muted); font-size: 0.88rem; margin-bottom: 1.25rem;'>"
        "Audit data provenance, run incremental session ingestion, evaluate historical predictions "
        "against observed actuals, and export database tables."
        "</p>",
        unsafe_allow_html=True,
    )

    t_archive, t_ingest, t_eval, t_backtest, t_backup = st.tabs(
        [
            "📜 Historical Archive",
            "📥 Ingestion & Provenance",
            "🎯 Prediction Verification",
            "🧪 Backtest Experiments",
            "💾 Export & Backup",
        ]
    )

    # -------------------------------------------------------------------------
    # TAB 1: Historical Race Archive
    # -------------------------------------------------------------------------
    with t_archive:
        st.markdown("#### 🏁 Stored Grand Prix Events & Alpine Results")
        events = db.get_events()
        if not events:
            st.info("No events in database. Use Ingestion tab to import data.")
        else:
            col_filter_s, col_count = st.columns([1.5, 3.5])
            seasons = sorted({e.get("season", 2024) for e in events}, reverse=True)
            with col_filter_s:
                filter_season = st.selectbox(
                    "Filter Season",
                    options=["All"] + [str(s) for s in seasons],
                    key="hist_filter_season",
                )

            with db.get_connection() as conn:
                q = """
                    SELECT e.season as Season, e.round_number as Round,
                           e.event_date as "Race Date",
                           e.event_name as "Grand Prix", e.location as Circuit,
                           s.session_type as Session, sr.driver_code as Driver,
                           sr.grid_position as Grid, sr.finish_position as Finish,
                           sr.points as Points, sr.finish_status as Status
                    FROM session_results sr
                    JOIN sessions s ON sr.session_id = s.id
                    JOIN events e ON s.event_id = e.id
                    WHERE (LOWER(sr.constructor_id) LIKE '%alpine%'
                           OR LOWER(sr.constructor_id) LIKE '%renault%')
                """
                params: list[object] = []
                if filter_season != "All":
                    q += " AND e.season = ?"
                    params.append(int(filter_season))
                q += " ORDER BY e.season DESC, e.round_number DESC, sr.finish_position ASC;"
                rows = conn.execute(q, params).fetchall()

            if rows:
                st.dataframe([dict(r) for r in rows], use_container_width=True, hide_index=True)
            else:
                st.info("No Alpine session results for selected season filter.")

    # -------------------------------------------------------------------------
    # TAB 2: Ingestion & Provenance Registry
    # -------------------------------------------------------------------------
    with t_ingest:
        st.markdown("#### 📥 Data Ingestion & Live Provenance Audit")

        ci1, ci2 = st.columns([1.5, 2.5])

        with ci1:
            st.markdown("##### Ingest Live Session (FastF1)")
            in_season = st.number_input(
                "Season", min_value=2021, max_value=2026, value=2024, step=1
            )
            in_round = st.number_input("Round Number", min_value=1, max_value=24, value=1, step=1)
            in_type = st.selectbox("Session Type", options=["Race", "Qualifying", "FP1", "FP2"])

            if st.button("🚀 Ingest Session via FastF1", type="primary"):
                progress_bar = st.progress(0.0)
                status_text = st.empty()

                def progress_cb(p: float, msg: str) -> None:
                    progress_bar.progress(p)
                    status_text.text(msg)

                pipeline = IngestionPipeline(db=db, parquet_store=store)
                try:
                    with st.spinner("Executing FastF1 ingestion..."):
                        sess_id = pipeline.ingest_session(
                            season=int(in_season),
                            round_number=int(in_round),
                            session_type=in_type,
                            progress_callback=progress_cb,
                        )
                        st.success(f"Successfully ingested session: `{sess_id}`")
                        st.rerun()
                except Exception as ex:
                    st.error(f"Ingestion failed: {ex}")

            st.markdown("---")
            if st.button("📥 Re-seed 2021–2026 Sample Data"):
                with st.spinner("Seeding database..."):
                    cnt = seed_database_with_f1_history(db, store)
                    st.success(f"Seeded {cnt} results across 2021–2026!")
                    st.rerun()

        with ci2:
            st.markdown("##### Data Provenance Registry")
            st.caption(
                "Source tracking table recording dataset keys, retrieval timestamps, "
                "schema versions, and SHA-256 integrity checksums."
            )
            with db.get_connection() as conn:
                p_rows = conn.execute(
                    """
                    SELECT dataset_key, source_id, season, retrieval_timestamp,
                           record_count, checksum
                    FROM source_provenance
                    ORDER BY retrieval_timestamp DESC
                    LIMIT 20;
                    """
                ).fetchall()

            if p_rows:
                st.dataframe([dict(r) for r in p_rows], use_container_width=True, hide_index=True)
            else:
                st.info("No provenance records registered yet.")

            st.markdown("##### Active Data Sources")
            sources = db.get_data_sources()
            st.dataframe(sources, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 3: Prediction Verification
    # -------------------------------------------------------------------------
    with t_eval:
        st.markdown("#### 🎯 Prediction History & Ground Truth Verification")
        st.markdown(
            "Every generated forecast is logged with its temporal cutoff, stage, "
            "predicted interval, and ground truth outcome once the race finishes."
        )

        evaluator = PredictionEvaluator(db=db)

        col_ev_btn, col_ev_stat = st.columns([1.5, 3.5])
        with col_ev_btn:
            if st.button("🔄 Auto-Evaluate Pending Predictions"):
                with st.spinner("Matching pending forecasts against observed race results..."):
                    updated = evaluator.auto_evaluate_pending()
                    st.success(f"Updated {updated} pending predictions with observed results!")
                    st.rerun()

        metrics = evaluator.evaluate_saved_predictions(target_type="RACE_FINISH_POS")

        # Scorecard KPIs
        sc1, sc2, sc3, sc4 = st.columns(4)
        mae_str = f"{metrics['mae']:.2f} pos" if metrics["mae"] is not None else "N/A"
        rmse_str = f"{metrics['rmse']:.2f} pos" if metrics["rmse"] is not None else "N/A"
        cov_str = (
            f"{metrics['interval_coverage_pct']:.1f}%"
            if metrics["interval_coverage_pct"] is not None
            else "N/A"
        )
        brier_str = f"{metrics['brier_score']:.3f}" if metrics["brier_score"] is not None else "N/A"

        sc1.metric("Historical MAE", mae_str)
        sc2.metric("Historical RMSE", rmse_str)
        sc3.metric("90% Interval Coverage", cov_str, "Nominal: 90.0%")
        sc4.metric("Points Brier Score", brier_str, "Lower is better")

        st.markdown("##### Saved Predictions Log")
        all_preds = db.get_predictions()
        if all_preds:
            display_preds = [
                {
                    "Created At": p["created_at"][:19],
                    "Stage": p["stage"],
                    "Target Event": p["target_event_id"],
                    "Type": p["target_type"],
                    "Predicted": round(float(p["predicted_value"]), 2),
                    "Interval": (
                        f"[{p['interval_low']:.1f}, {p['interval_high']:.1f}]"
                        if p.get("interval_low") is not None
                        else "-"
                    ),
                    "Actual": (
                        round(float(p["actual_value"]), 2)
                        if p.get("actual_value") is not None
                        else "Pending"
                    ),
                    "Error": (
                        f"{float(p['error']):+.2f}" if p.get("error") is not None else "-"
                    ),
                    "Evaluated": "✅" if p["is_evaluated"] else "⏳ Pending",
                }
                for p in all_preds
            ]
            st.dataframe(display_preds, use_container_width=True, hide_index=True)
        else:
            st.info("No predictions saved in database yet.")

    # -------------------------------------------------------------------------
    # TAB 4: Backtest Experiments
    # -------------------------------------------------------------------------
    with t_backtest:
        st.markdown("#### 🧪 Chronological Walk-Forward Backtest Benchmarks")
        st.markdown(
            "Rigorous, strictly chronological evaluation training on prior seasons and "
            "testing on subsequent seasons with zero future information leakage."
        )

        col_bt1, col_bt2 = st.columns([1.5, 3.5])

        with col_bt1:
            st.markdown("##### Run Walk-Forward Experiment")
            train_s = st.multiselect(
                "Training Seasons",
                options=[2021, 2022, 2023],
                default=[2023],
            )
            test_s = st.selectbox("Test Season", options=[2024, 2026], index=0)

            if st.button("⚡ Execute Chronological Backtest"):
                with st.spinner("Executing walk-forward evaluation across calendar..."):
                    bt = ChronologicalBacktester(db=db, parquet_store=store)
                    res = bt.run_backtest(train_seasons=train_s, test_seasons=[test_s])
                    st.success(
                        f"Backtest completed! MAE: {res.mae:.2f} pos, RMSE: {res.rmse:.2f} pos"
                    )
                    st.rerun()

        with col_bt2:
            st.markdown("##### Logged Research Experiments")
            experiments = db.get_experiments()
            if experiments:
                st.dataframe(experiments, use_container_width=True, hide_index=True)
            else:
                st.info("No backtesting experiments recorded yet. Execute a backtest to log one.")

    # -------------------------------------------------------------------------
    # TAB 5: Export & Backup
    # -------------------------------------------------------------------------
    with t_backup:
        st.markdown("#### 💾 Database Online Backup & Relational CSV Export")

        cb1, cb2 = st.columns(2)

        with cb1:
            st.markdown("##### SQLite Online Backup")
            st.caption(
                "Creates a timestamped, non-blocking online backup copy of `stratos.db` "
                "in `data/backups/`."
            )
            if st.button("📦 Create Online Database Backup", type="primary"):
                backup_dir = Path("data/backups")
                backup_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                b_file = backup_dir / f"stratos_backup_{ts}.db"
                db.create_backup(b_file)
                st.success(f"Backup created successfully at: `{b_file}`")

        with cb2:
            st.markdown("##### CSV Table Exports")
            st.caption("Export raw database tables directly for external spreadsheet analysis.")

            for tbl in ["events", "sessions", "session_results", "predictions"]:
                csv_data = db.export_table_to_csv(tbl)
                st.download_button(
                    label=f"📥 Download {tbl}.csv",
                    data=csv_data,
                    file_name=f"{tbl}.csv",
                    mime="text/csv",
                    key=f"dl_{tbl}",
                )
