"""STRATOS Data Management Module.

Provides loaders, caching utilities, and interfaces for Formula 1 session
and telemetry data using FastF1.
"""

from stratos.data.loader import configure_cache, load_session

__all__ = ["configure_cache", "load_session"]
