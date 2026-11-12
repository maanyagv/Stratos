#!/usr/bin/env python3
"""Race inspection utility script for STRATOS.

Loads a historical Formula 1 session via FastF1, inspects session attributes,
and prints available lap and weather columns along with sample lap records.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from stratos import load_config
from stratos.data import load_session

logger = logging.getLogger("stratos.inspect_race")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for session inspection."""
    parser = argparse.ArgumentParser(
        description="Inspect a historical Formula 1 session using STRATOS FastF1 loader."
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Championship season year (e.g., 2023). Defaults to value in config.",
    )
    parser.add_argument(
        "--event",
        type=str,
        default=None,
        help="Grand Prix name (e.g., 'Monaco') or round number. Defaults to value in config.",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session identifier ('R', 'Q', 'FP1', etc.). Defaults to value in config.",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Custom cache directory path. Defaults to value in config.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Number of sample lap records to display (default: 5).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML configuration file (default: configs/default.yaml).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable FastF1 disk caching.",
    )
    return parser.parse_args()


def format_columns(columns: list[str], indent: int = 4, max_per_line: int = 5) -> str:
    """Format a list of column names for readable console output."""
    lines: list[str] = []
    prefix = " " * indent
    for i in range(0, len(columns), max_per_line):
        chunk = columns[i : i + max_per_line]
        lines.append(prefix + ", ".join(chunk))
    return "\n".join(lines)


def get_safe_session_attributes(session: Any) -> list[str]:
    """Inspect and return available session properties without triggering DataNotLoadedError."""
    available: list[str] = []
    for attr in dir(session):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(session, attr)
            if not callable(val):
                available.append(attr)
        except Exception:
            # Property exists on session class but was not requested or loaded
            continue
    return sorted(available)


def inspect_session(
    season: int,
    event: str | int,
    session_id: str,
    cache_dir: str | None,
    sample_size: int,
) -> None:
    """Load session and print comprehensive structure, column, and sample data.

    Parameters
    ----------
    season : int
        Championship year.
    event : str or int
        Event name or round number.
    session_id : str
        Session identifier ('R', 'Q', etc.).
    cache_dir : str or None
        Path to cache directory, or None if disabled.
    sample_size : int
        Number of lap rows to display.
    """
    separator = "=" * 80
    sub_separator = "-" * 80

    print(separator)
    print("STRATOS FORMULA 1 SESSION INSPECTOR")
    print(separator)
    print(f"Target: Season {season} | Event '{event}' | Session '{session_id}'")
    print(f"Cache:  {cache_dir if cache_dir else 'Disabled'}")
    print(sub_separator)
    print("Loading session data from FastF1 backend...")

    try:
        session = load_session(
            season=season,
            event=event,
            session_id=session_id,
            cache_dir=cache_dir,
            laps=True,
            telemetry=False,
            weather=True,
            messages=True,
        )
    except Exception as exc:
        print("\n[ERROR] Failed to load session data:")
        print(f"  {exc}")
        print("\nTroubleshooting notes:")
        print("  - If offline, cached data is required under the cache directory.")
        print("  - If running for the first time, an active internet connection is required.")
        print("  - Verify that the season, event name, and session identifier are valid.")
        sys.exit(1)

    print("\n[SUCCESS] Session successfully loaded!")
    print(separator)
    print("1. SESSION METADATA")
    print(separator)
    event_info: Any = getattr(session, "event", None)
    if event_info is not None:
        country = event_info.get("Country", "N/A")
        location = event_info.get("Location", "N/A")
        print(f"  Official Event Name : {event_info.get('OfficialEventName', 'N/A')}")
        print(f"  Event Name          : {event_info.get('EventName', 'N/A')}")
        print(f"  Country / Location  : {country} ({location})")
        print(f"  Event Date          : {event_info.get('EventDate', 'N/A')}")
        print(f"  Round Number        : {event_info.get('RoundNumber', 'N/A')}")
    else:
        print(f"  Session Name        : {session.name}")
        print(f"  Date                : {session.date}")

    # Available session properties
    session_attrs = get_safe_session_attributes(session)
    print(f"\n  Available Session Attributes ({len(session_attrs)}):")
    print(format_columns(session_attrs, indent=4, max_per_line=4))

    # 2. LAP DATA
    print("\n" + separator)
    print("2. LAP TIMING & TELEMETRY SUMMARY")
    print(separator)
    laps_df = getattr(session, "laps", None)

    if laps_df is not None and not laps_df.empty:
        lap_cols = list(laps_df.columns)
        print(f"  Total Laps Recorded : {len(laps_df)}")
        if "Driver" in laps_df.columns:
            drivers = sorted(laps_df["Driver"].dropna().unique().tolist())
            print(f"  Drivers Participating ({len(drivers)}): {', '.join(drivers)}")
        print(f"  Lap DataFrame Shape : {laps_df.shape}")
        print(f"\n  Available Lap Columns ({len(lap_cols)}):")
        print(format_columns(lap_cols, indent=4, max_per_line=4))

        # Sample preview
        preview_cols = [
            col
            for col in [
                "Driver",
                "LapNumber",
                "LapTime",
                "Compound",
                "TyreLife",
                "Stint",
                "PitInTime",
                "PitOutTime",
                "TrackStatus",
            ]
            if col in laps_df.columns
        ]
        if not preview_cols:
            preview_cols = lap_cols[:8]

        sample_count = min(sample_size, len(laps_df))
        print(f"\n  Sample Lap Records (First {sample_count} rows, key columns):")
        print(sub_separator)
        sample_df = laps_df[preview_cols].head(sample_count)
        print(sample_df.to_string(index=False))
        print(sub_separator)
    else:
        print("  [WARN] No lap records available for this session.")

    # 3. WEATHER DATA
    print("\n" + separator)
    print("3. WEATHER DATA SUMMARY")
    print(separator)
    weather_df = getattr(session, "weather_data", None)

    if weather_df is not None and not weather_df.empty:
        weather_cols = list(weather_df.columns)
        print(f"  Total Weather Samples: {len(weather_df)}")
        print(f"  Weather Data Shape   : {weather_df.shape}")
        print(f"\n  Available Weather Columns ({len(weather_cols)}):")
        print(format_columns(weather_cols, indent=4, max_per_line=4))

        sample_weather_count = min(sample_size, len(weather_df))
        print(f"\n  Sample Weather Records (First {sample_weather_count} rows):")
        print(sub_separator)
        print(weather_df.head(sample_weather_count).to_string(index=False))
        print(sub_separator)
    else:
        print("  [WARN] No weather records available for this session.")

    print("\n" + separator)
    print("Inspection complete. Data structures verified for STRATOS pipeline.")
    print(separator)


def main() -> None:
    """Script entry point."""
    args = parse_args()

    # Load configuration
    try:
        cfg = load_config(args.config)
    except Exception as exc:
        logger.warning("Could not load config file (%s). Using fallback defaults.", exc)
        cfg = {}

    data_cfg = cfg.get("data", {})

    season = args.season if args.season is not None else data_cfg.get("default_season", 2023)
    event = args.event if args.event is not None else data_cfg.get("default_event", "Monaco")
    session_id = args.session if args.session is not None else data_cfg.get("default_session", "R")

    if args.no_cache:
        cache_dir = None
    elif args.cache_dir is not None:
        cache_dir = args.cache_dir
    else:
        cache_dir = data_cfg.get("cache_dir", "data/cache")

    inspect_session(
        season=season,
        event=event,
        session_id=session_id,
        cache_dir=cache_dir,
        sample_size=args.sample_size,
    )


if __name__ == "__main__":
    main()
