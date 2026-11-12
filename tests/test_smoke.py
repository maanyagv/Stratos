"""Smoke and unit tests for STRATOS foundation.

Ensures package structure, configuration loading, FastF1 session loader,
and error handling behave correctly completely offline without internet access.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from stratos import __version__, get_project_root, load_config
from stratos.data import configure_cache, load_session


def test_package_imports() -> None:
    """Verify that stratos and its submodules import cleanly."""
    import stratos
    import stratos.data
    import stratos.data.loader

    assert stratos.__version__ == "0.1.0"
    assert __version__ == "0.1.0"
    assert hasattr(stratos.data, "load_session")
    assert hasattr(stratos.data, "configure_cache")
    assert hasattr(stratos.data.loader, "load_session")


def test_project_root_resolution() -> None:
    """Verify that get_project_root points to an existing directory containing pyproject.toml."""
    root = get_project_root()
    assert isinstance(root, Path)
    assert root.is_dir()
    assert (root / "pyproject.toml").is_file()


def test_load_config_default() -> None:
    """Verify loading the repository's default configuration."""
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "project" in cfg
    assert "data" in cfg
    assert "logging" in cfg

    assert cfg["project"]["name"] == "stratos"
    assert cfg["data"]["cache_dir"] == "data/cache"
    assert cfg["data"]["default_season"] == 2023
    assert cfg["data"]["default_event"] == "Monaco"
    assert cfg["data"]["default_session"] == "R"


def test_load_config_custom_file(tmp_path: Path) -> None:
    """Verify loading configuration from a custom path."""
    custom_cfg_path = tmp_path / "custom.yaml"
    custom_cfg_path.write_text("experiment:\n  name: 'test_run'\n  seed: 123\n", encoding="utf-8")

    cfg = load_config(custom_cfg_path)
    assert cfg == {"experiment": {"name": "test_run", "seed": 123}}


def test_load_config_missing_file(tmp_path: Path) -> None:
    """Verify that attempting to load a missing config file raises FileNotFoundError."""
    missing_file = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config(missing_file)


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    """Verify that malformed or non-dictionary YAML raises ValueError."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a dictionary/mapping"):
        load_config(invalid_yaml)


def test_configure_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify cache directory creation and FastF1 cache initialization."""
    mock_enable = MagicMock()
    monkeypatch.setattr("fastf1.Cache.enable_cache", mock_enable)

    target_cache = tmp_path / "test_cache_dir"
    assert not target_cache.exists()

    result = configure_cache(target_cache)
    assert result == target_cache.resolve()
    assert target_cache.is_dir()
    mock_enable.assert_called_once_with(str(target_cache.resolve()))


def test_configure_cache_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that FastF1 cache initialization failures raise RuntimeError."""

    def _failing_enable(path: str) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr("fastf1.Cache.enable_cache", _failing_enable)

    target_cache = tmp_path / "cache_fail"
    with pytest.raises(RuntimeError, match="Failed to enable FastF1 cache"):
        configure_cache(target_cache)


@pytest.mark.parametrize(
    ("season", "event", "session_id", "expected_err"),
    [
        (1949, "Monaco", "R", "Invalid season '1949'"),
        (2023, "", "R", "Event name must not be empty"),
        (2023, "   ", "R", "Event name must not be empty"),
        (2023, 0, "R", "Round number must be >= 1"),
        (2023, -2, "R", "Round number must be >= 1"),
        (2023, "Monaco", "", "Session identifier must be a non-empty string"),
        (2023, "Monaco", "   ", "Session identifier must be a non-empty string"),
    ],
)
def test_load_session_validation(
    season: int, event: str | int, session_id: str, expected_err: str
) -> None:
    """Verify input validation triggers ValueError for invalid session identifiers."""
    with pytest.raises(ValueError, match=expected_err):
        load_session(season, event, session_id)


def test_load_session_mocked_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify load_session workflow executes offline using mocked FastF1 components."""
    mock_session = MagicMock()
    mock_session.load = MagicMock()

    mock_get_session = MagicMock(return_value=mock_session)
    mock_enable_cache = MagicMock()

    monkeypatch.setattr("fastf1.get_session", mock_get_session)
    monkeypatch.setattr("fastf1.Cache.enable_cache", mock_enable_cache)

    custom_cache = tmp_path / "cache"
    session = load_session(
        season=2023,
        event="Monaco",
        session_id="R",
        cache_dir=custom_cache,
        laps=True,
        telemetry=False,
        weather=True,
        messages=True,
    )

    assert session is mock_session
    mock_get_session.assert_called_once_with(2023, "Monaco", "R")
    mock_session.load.assert_called_once_with(
        laps=True,
        telemetry=False,
        weather=True,
        messages=True,
    )


def test_load_session_get_session_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify load_session raises RuntimeError without fabricating data when get_session fails."""
    monkeypatch.setattr("fastf1.Cache.enable_cache", MagicMock())

    def _failing_get_session(year: int, event: str, session: str) -> None:
        raise KeyError("Session not found in official schedule")

    monkeypatch.setattr("fastf1.get_session", _failing_get_session)

    with pytest.raises(RuntimeError, match="Failed to locate session"):
        load_session(2023, "NonExistentGrandPrix", "R", cache_dir=None)


def test_load_session_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify load_session raises RuntimeError without fabricating data when session.load fails."""
    monkeypatch.setattr("fastf1.Cache.enable_cache", MagicMock())

    mock_session = MagicMock()
    mock_session.load.side_effect = ConnectionError("Could not reach Ergast/FastF1 backend")
    monkeypatch.setattr("fastf1.get_session", MagicMock(return_value=mock_session))

    with pytest.raises(RuntimeError, match="Failed to load data for session"):
        load_session(2023, "Monaco", "R", cache_dir=None)
