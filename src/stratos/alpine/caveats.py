"""Scientific and regulatory caveats for Formula 1 performance analysis.

Documents limitations of public telemetry data, proxy indicators, and technical
regulation transitions (e.g. 2022 Ground Effect, 2026 Active Aero).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegulationEra:
    """Historical Formula 1 technical regulation era metadata."""

    era_name: str
    seasons: tuple[int, ...]
    aerodynamics_philosophy: str
    engine_formula: str
    tyre_spec: str
    notes: str


REGULATION_ERAS: dict[str, RegulationEra] = {
    "HYBRID_HIGH_RAKE": RegulationEra(
        era_name="V6 Turbo Hybrid High-Downforce (2017-2021)",
        seasons=(2017, 2018, 2019, 2020, 2021),
        aerodynamics_philosophy="Over-body downforce with complex bargeboards and high rake.",
        engine_formula="1.6L V6 Turbo Hybrid with MGU-K and MGU-H.",
        tyre_spec="13-inch wheels with Pirelli compounds.",
        notes="High wake turbulence; difficult to follow closely without DRS.",
    ),
    "GROUND_EFFECT": RegulationEra(
        era_name="Ground Effect Venturi Era (2022-2025)",
        seasons=(2022, 2023, 2024, 2025),
        aerodynamics_philosophy=(
            "Underfloor Venturi tunnels, simplified front wings, wheel winglets."
        ),
        engine_formula="1.6L V6 Turbo Hybrid with E10 fuel freeze.",
        tyre_spec="18-inch low-profile tyres.",
        notes="Susceptible to porpoising and stiff mechanical ride heights.",
    ),
    "ACTIVE_AERO_2026": RegulationEra(
        era_name="Active Aerodynamics & 50/50 Electrical Power (2026+)",
        seasons=(2026, 2027, 2028),
        aerodynamics_philosophy="Active front and rear wings (X-mode straight, Z-mode cornering).",
        engine_formula="1.6L V6 Turbo Hybrid without MGU-H; 350kW MGU-K electrical power.",
        tyre_spec="18-inch slightly narrower Pirelli tyres.",
        notes="Substantial shift in energy deployment strategy and straight-line drag reduction.",
    ),
}

METRIC_PROXIES: dict[str, str] = {
    "speed_trap_max": (
        "Proxy for straight-line efficiency and engine deployment. "
        "Limitation: Confounded by tow/slipstream, DRS state, battery SoC, "
        "downforce wing configuration, and exit speed from previous corner."
    ),
    "tyre_degradation_slope": (
        "Proxy for tyre degradation rate (seconds added per lap of tyre age). "
        "Limitation: Confounded by fuel burn-off (~0.033s/lap), tyre management directives, "
        "traffic, dirty air, and track rubber evolution."
    ),
    "clean_lap_median": (
        "Proxy for baseline race pace in undisturbed air. "
        "Limitation: Sample size limited by traffic and pit windows; requires normalization "
        "across different tracks to make cross-circuit comparisons valid."
    ),
    "pit_lane_time_loss": (
        "Proxy for operational pit lane execution. "
        "Limitation: Total pit lane transit includes speed limit compliance (60 or 80 km/h) "
        "and traffic box delays, not exclusively stationary wheel-gun mechanics."
    ),
    "qualifying_pace_delta": (
        "Proxy for single-lap peak aerodynamic and mechanical grip. "
        "Limitation: Sensitive to track temperature fluctuations between Q1 and Q3, "
        "traffic on out-laps, and wind gust changes."
    ),
}


def get_regulation_era(season: int) -> RegulationEra:
    """Return the technical regulation era metadata for a given championship season.

    Parameters
    ----------
    season : int
        Championship season.

    Returns
    -------
    RegulationEra
        Technical and aerodynamic era metadata.
    """
    for era in REGULATION_ERAS.values():
        if season in era.seasons:
            return era
    if season >= 2026:
        return REGULATION_ERAS["ACTIVE_AERO_2026"]
    return REGULATION_ERAS["HYBRID_HIGH_RAKE"]


def get_proxy_caveat(metric_name: str) -> str:
    """Retrieve the documented limitations and proxy definition for a metric.

    Parameters
    ----------
    metric_name : str
        Name of metric (e.g. 'speed_trap_max', 'tyre_degradation_slope').

    Returns
    -------
    str
        Caveat text explaining limitations.
    """
    return METRIC_PROXIES.get(
        metric_name,
        "Proxy metric derived from public timing and telemetry. Interpret with caution.",
    )
