"""Unit tests for Alpine regulatory caveats and proxy definitions."""

from __future__ import annotations

from stratos.alpine.caveats import get_proxy_caveat, get_regulation_era


def test_regulation_eras() -> None:
    """Verify technical regulation era mapping and transition metadata."""
    era_2020 = get_regulation_era(2020)
    assert "High-Downforce" in era_2020.era_name
    assert "MGU-H" in era_2020.engine_formula

    era_2024 = get_regulation_era(2024)
    assert "Ground Effect" in era_2024.era_name
    assert "Venturi" in era_2024.aerodynamics_philosophy

    era_2026 = get_regulation_era(2026)
    assert "Active Aerodynamics" in era_2026.era_name
    assert "without MGU-H" in era_2026.engine_formula


def test_proxy_caveats() -> None:
    """Verify proxy caveat explanations for sensitive metrics."""
    speed_cav = get_proxy_caveat("speed_trap_max")
    assert "Proxy for straight-line efficiency" in speed_cav
    assert "tow/slipstream" in speed_cav

    deg_cav = get_proxy_caveat("tyre_degradation_slope")
    assert "fuel burn-off" in deg_cav

    lap_cav = get_proxy_caveat("clean_lap_median")
    assert "normalization" in lap_cav
