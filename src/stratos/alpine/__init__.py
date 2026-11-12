"""Alpine performance analysis and identity tracking subsystem for STRATOS.

Exports constructor identity mapping, performance metrics calculators,
scientific caveats, and high-level comparative benchmarkers.
"""

from stratos.alpine.caveats import REGULATION_ERAS, get_proxy_caveat, get_regulation_era
from stratos.alpine.comparator import AlpinePerformanceComparator
from stratos.alpine.identity import (
    ConstructorIdentity,
    DriverIdentity,
    get_alpine_drivers_for_season,
    get_season_rivals,
    map_constructor,
    map_driver,
)
from stratos.alpine.metrics import (
    calculate_clean_lap_pace,
    calculate_normalized_pace,
    calculate_pit_performance,
    calculate_qualifying_performance,
    calculate_reliability_stats,
    calculate_sector_performance,
    calculate_speed_trap_performance,
    calculate_teammate_comparison,
    calculate_tyre_degradation,
)

__all__ = [
    "REGULATION_ERAS",
    "AlpinePerformanceComparator",
    "ConstructorIdentity",
    "DriverIdentity",
    "calculate_clean_lap_pace",
    "calculate_normalized_pace",
    "calculate_pit_performance",
    "calculate_qualifying_performance",
    "calculate_reliability_stats",
    "calculate_sector_performance",
    "calculate_speed_trap_performance",
    "calculate_teammate_comparison",
    "calculate_tyre_degradation",
    "get_alpine_drivers_for_season",
    "get_proxy_caveat",
    "get_regulation_era",
    "get_season_rivals",
    "map_constructor",
    "map_driver",
]
