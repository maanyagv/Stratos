"""STRATOS: Research-Oriented Agentic AI for Motorsport Race Strategy.

STRATOS investigates risk-aware deliberative multi-agent decision-making
for explainable Formula 1 race strategy under uncertainty.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from stratos import agents, alpine, data, ingestion, models, prediction, storage

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "agents",
    "alpine",
    "data",
    "get_project_root",
    "ingestion",
    "load_config",
    "models",
    "prediction",
    "storage",
]

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """Return the repository root directory Path.

    Returns
    -------
    Path
        Resolved path pointing to the project root.
    """
    # src/stratos/__init__.py -> parents[2] is the project root
    return Path(__file__).resolve().parents[2]


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load project configuration from a YAML file.

    Parameters
    ----------
    config_path : str or Path or None, default None
        Path to YAML configuration file. If None, resolves to
        `configs/default.yaml` relative to current working directory
        or repository root.

    Returns
    -------
    dict[str, Any]
        Parsed configuration dictionary.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.
    ValueError
        If the YAML file cannot be parsed or does not contain a valid mapping.
    """
    if config_path is not None:
        target_path = Path(config_path).resolve()
    else:
        # Check current working directory first, then package root
        candidate_cwd = Path.cwd() / "configs" / "default.yaml"
        candidate_root = get_project_root() / "configs" / "default.yaml"

        if candidate_cwd.is_file():
            target_path = candidate_cwd.resolve()
        elif candidate_root.is_file():
            target_path = candidate_root.resolve()
        else:
            target_path = candidate_cwd.resolve()

    if not target_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found at '{target_path}'. "
            "Ensure configs/default.yaml exists or provide an explicit path."
        )

    try:
        with open(target_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML configuration at '{target_path}': {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid configuration at '{target_path}': "
            f"expected a dictionary/mapping, got {type(data).__name__}."
        )

    return data
