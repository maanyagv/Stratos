"""FastF1 data loading and caching module for STRATOS.

Provides reproducible data acquisition for historical Formula 1 sessions,
caching responses locally under data/cache/ to avoid redundant network overhead.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import fastf1

if TYPE_CHECKING:
    import fastf1.core

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR: str = "data/cache"
MIN_F1_SEASON: int = 1950


def configure_cache(cache_dir: str | Path = DEFAULT_CACHE_DIR) -> Path:
    """Ensure local cache directory exists and enable FastF1 caching.

    Parameters
    ----------
    cache_dir : str or Path, default "data/cache"
        Path to local directory where FastF1 session artifacts will be cached.

    Returns
    -------
    Path
        Resolved Path object for the configured cache directory.

    Raises
    ------
    RuntimeError
        If cache directory cannot be created or FastF1 cache initialization fails.
    """
    try:
        cache_path = Path(cache_dir).resolve()
        cache_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Failed to create cache directory at '{cache_dir}': {exc}") from exc

    try:
        fastf1.Cache.enable_cache(str(cache_path))
        logger.debug("FastF1 cache enabled at: %s", cache_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to enable FastF1 cache at '{cache_path}': {exc}") from exc

    return cache_path


def load_session(
    season: int,
    event: str | int,
    session_id: str = "R",
    *,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
    laps: bool = True,
    telemetry: bool = False,
    weather: bool = True,
    messages: bool = True,
) -> fastf1.core.Session:
    """Load a Formula 1 session using FastF1 with validation and error handling.

    Parameters
    ----------
    season : int
        Championship season year (e.g., 2023). Must be >= 1950.
    event : str or int
        Grand Prix name (e.g. 'Monaco', 'Silverstone') or 1-indexed round number.
    session_id : str, default 'R'
        Session identifier: 'FP1', 'FP2', 'FP3', 'Q', 'SQ', 'S', or 'R' (Race).
    cache_dir : str, Path, or None, default 'data/cache'
        Path to directory for caching raw responses. If None, caching is bypassed.
    laps : bool, default True
        Whether to load lap timing and compound data.
    telemetry : bool, default False
        Whether to load high-frequency car telemetry (speed, throttle, brake, DRS).
    weather : bool, default True
        Whether to load track and ambient weather condition samples.
    messages : bool, default True
        Whether to load race control messages (flags, safety car status).

    Returns
    -------
    fastf1.core.Session
        Loaded FastF1 session with requested attributes populated.

    Raises
    ------
    ValueError
        If season, event, or session_id arguments fail validation.
    RuntimeError
        If fetching session data fails due to network, API, or parser errors.
        Does not fabricate synthetic or fallback data.
    """
    # 1. Parameter Validation
    if not isinstance(season, int) or season < MIN_F1_SEASON:
        raise ValueError(
            f"Invalid season '{season}'. F1 World Championship seasons "
            f"must be an integer >= {MIN_F1_SEASON}."
        )

    if isinstance(event, str):
        if not event.strip():
            raise ValueError("Event name must not be empty or whitespace.")
        event_query: Any = event.strip()
    elif isinstance(event, int):
        if event < 1:
            raise ValueError(f"Round number must be >= 1, got {event}.")
        event_query = event
    else:
        raise ValueError(f"Invalid event type '{type(event).__name__}'. Expected str or int.")

    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Session identifier must be a non-empty string (e.g., 'R', 'Q', 'FP1').")
    clean_session_id = session_id.strip()

    # 2. Configure Cache
    if cache_dir is not None:
        configure_cache(cache_dir)

    # 3. Retrieve Session Object
    try:
        session = fastf1.get_session(season, event_query, clean_session_id)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to locate session for season={season}, event={event_query!r}, "
            f"session={clean_session_id!r}: {exc}"
        ) from exc

    # 4. Load Session Data
    try:
        session.load(
            laps=laps,
            telemetry=telemetry,
            weather=weather,
            messages=messages,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load data for session '{session}': {exc}. "
            "Verify internet connectivity, session name, and FastF1 availability."
        ) from exc

    return session
