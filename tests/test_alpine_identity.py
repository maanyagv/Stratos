"""Unit tests for Alpine and constructor season-aware identity mapping."""

from __future__ import annotations

from stratos.alpine.identity import (
    get_alpine_drivers_for_season,
    get_season_rivals,
    map_constructor,
    map_driver,
)


def test_alpine_constructor_mapping_2021_plus() -> None:
    """Verify 2021+ Alpine is correctly flagged as Alpine-branded and Enstone heritage."""
    id_2021 = map_constructor("Alpine", 2021)
    assert id_2021.constructor_id == "alpine"
    assert id_2021.is_alpine_branded is True
    assert id_2021.is_enstone_heritage is True
    assert "Alpine Era" in id_2021.heritage_era

    id_2024 = map_constructor("BWT Alpine F1 Team", 2024)
    assert id_2024.constructor_id == "alpine"
    assert id_2024.is_alpine_branded is True
    assert id_2024.is_enstone_heritage is True


def test_renault_and_lotus_heritage_mapping() -> None:
    """Verify pre-2021 Renault and Lotus are Enstone heritage, but NOT Alpine branded."""
    id_renault_2020 = map_constructor("Renault DP World F1 Team", 2020)
    assert id_renault_2020.constructor_id == "renault"
    assert id_renault_2020.is_alpine_branded is False
    assert id_renault_2020.is_enstone_heritage is True
    assert "Renault Works II" in id_renault_2020.heritage_era

    id_lotus_2013 = map_constructor("Lotus F1 Team", 2013)
    assert id_lotus_2013.constructor_id == "lotus"
    assert id_lotus_2013.is_alpine_branded is False
    assert id_lotus_2013.is_enstone_heritage is True


def test_rival_constructors_mapping() -> None:
    """Verify competitor constructors are neither Alpine branded nor Enstone heritage."""
    rbr = map_constructor("Oracle Red Bull Racing", 2024)
    assert rbr.constructor_id == "red_bull"
    assert rbr.is_alpine_branded is False
    assert rbr.is_enstone_heritage is False

    fer = map_constructor("Ferrari", 2024)
    assert fer.constructor_id == "ferrari"
    assert fer.is_alpine_branded is False
    assert fer.is_enstone_heritage is False

    mcl = map_constructor("McLaren Formula 1 Team", 2024)
    assert mcl.constructor_id == "mclaren"
    assert mcl.is_alpine_branded is False
    assert mcl.is_enstone_heritage is False


def test_driver_identity_mapping() -> None:
    """Verify driver code lookup, Alpine affiliation, and competitor drivers."""
    gas = map_driver("GAS", season=2024)
    assert gas.driver_code == "GAS"
    assert gas.full_name == "Pierre Gasly"
    assert gas.is_alpine_driver is True

    # Esteban Ocon in 2024 vs 2025
    oco_2024 = map_driver("OCO", season=2024)
    assert oco_2024.is_alpine_driver is True
    oco_2025 = map_driver("OCO", season=2025)
    assert oco_2025.is_alpine_driver is False

    # Jack Doohan in 2025/2026
    doo = map_driver("DOO", season=2025)
    assert doo.is_alpine_driver is True

    # Competitor driver
    ver = map_driver("VER", season=2024)
    assert ver.is_alpine_driver is False


def test_dynamic_season_rivals() -> None:
    """Verify dynamic midfield rivals by championship year."""
    rivals_2021 = get_season_rivals(2021)
    assert "alphatauri" in rivals_2021

    rivals_2024 = get_season_rivals(2024)
    assert "haas" in rivals_2024
    assert "williams" in rivals_2024


def test_alpine_drivers_for_season() -> None:
    """Verify retrieving Alpine drivers by season."""
    alp_2024 = get_alpine_drivers_for_season(2024)
    assert "GAS" in alp_2024
    assert "OCO" in alp_2024
    assert "VER" not in alp_2024
