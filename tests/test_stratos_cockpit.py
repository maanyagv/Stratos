"""Integration tests for the four primary STRATOS cockpit navigation views."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from stratos.dashboard.views.history_data import render_history_data_view
from stratos.dashboard.views.next_race import render_next_race_view
from stratos.dashboard.views.overview import render_overview_view
from stratos.dashboard.views.team_analysis import render_team_analysis_view
from stratos.storage.database import StratosDB
from stratos.storage.parquet_store import ParquetStore
from stratos.storage.sample_data import seed_database_with_f1_history


@pytest.fixture
def test_env() -> tuple[StratosDB, ParquetStore, Path]:
    """Provide isolated SQLite database and parquet store."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t_path = Path(tmp)
        db = StratosDB(db_path=t_path / "stratos.db")
        store = ParquetStore(root_dir=t_path / "processed")
        yield db, store, t_path


def test_overview_view_empty_and_seeded(test_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify Overview cockpit renders empty state and populated state."""
    db, _, _ = test_env

    # 1. Empty state
    render_overview_view(db=db)

    # 2. Seed database
    cnt = seed_database_with_f1_history(db)
    assert cnt > 0
    assert len(db.get_events()) > 0

    # 3. Populated state
    render_overview_view(db=db)


def test_team_analysis_view_rendering(test_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify Team Analysis cockpit renders with multi-season database records."""
    db, _, _ = test_env
    seed_database_with_f1_history(db)

    render_team_analysis_view(db=db)


def test_next_race_view_rendering(test_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify Next Race forecast and explainability view renders without error."""
    db, _, _ = test_env
    seed_database_with_f1_history(db)

    render_next_race_view(db=db)


def test_history_data_view_rendering(test_env: tuple[StratosDB, ParquetStore, Path]) -> None:
    """Verify History & Data cockpit renders archive, provenance, and backups."""
    db, store, _ = test_env
    seed_database_with_f1_history(db, store)

    render_history_data_view(db=db, store=store)


def test_next_race_telemetry_discussion_direct() -> None:
    """Verify engineer telemetry and multi-agent discussion sub-tab renders directly."""
    from stratos.dashboard.views.next_race import _render_telemetry_discussion_tab

    _render_telemetry_discussion_tab()

