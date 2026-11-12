"""Alpine F1 Team identification and season-aware constructor mapping.

Distinguishes Alpine-branded seasons (2021+) from earlier Renault and Enstone team identities,
maintains stable driver/constructor keys, and provides dynamic rival mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConstructorIdentity:
    """Standardized representation of a Formula 1 constructor in a specific season."""

    constructor_id: str
    name: str
    season: int
    is_alpine_branded: bool
    is_enstone_heritage: bool
    heritage_era: str


@dataclass(frozen=True)
class DriverIdentity:
    """Standardized representation of a Formula 1 driver."""

    driver_code: str
    driver_number: str
    full_name: str
    nationality: str
    is_alpine_driver: bool


# Season-by-season direct competitors for Alpine / Enstone midfield benchmarking
SEASON_RIVALS: dict[int, list[str]] = {
    2018: ["haas", "mclaren", "force_india"],
    2019: ["mclaren", "toro_rosso", "racing_point"],
    2020: ["mclaren", "racing_point", "ferrari"],
    2021: ["alphatauri", "aston_martin", "ferrari"],
    2022: ["mclaren", "alfa_romeo", "aston_martin"],
    2023: ["mclaren", "aston_martin", "williams"],
    2024: ["haas", "williams", "rb", "sauber"],
    2025: ["haas", "williams", "rb", "aston_martin"],
    2026: ["haas", "williams", "rb", "audi"],
}

# Known drivers associated with Alpine / Renault Enstone operations
KNOWN_DRIVERS: dict[str, dict[str, Any]] = {
    "GAS": {
        "number": "10",
        "name": "Pierre Gasly",
        "nationality": "FRA",
        "alpine_seasons": [2023, 2024, 2025, 2026],
    },
    "OCO": {
        "number": "31",
        "name": "Esteban Ocon",
        "nationality": "FRA",
        "alpine_seasons": [2020, 2021, 2022, 2023, 2024],
    },
    "DOO": {
        "number": "61",
        "name": "Jack Doohan",
        "nationality": "AUS",
        "alpine_seasons": [2024, 2025, 2026],
    },
    "ALO": {
        "number": "14",
        "name": "Fernando Alonso",
        "nationality": "ESP",
        "alpine_seasons": [2003, 2004, 2005, 2006, 2008, 2009, 2021, 2022],
    },
    "PIA": {
        "number": "81",
        "name": "Oscar Piastri",
        "nationality": "AUS",
        "alpine_seasons": [],
    },
    "RIC": {
        "number": "3",
        "name": "Daniel Ricciardo",
        "nationality": "AUS",
        "alpine_seasons": [2019, 2020],
    },
    "HUL": {
        "number": "27",
        "name": "Nico Hülkenberg",
        "nationality": "GER",
        "alpine_seasons": [2017, 2018, 2019],
    },
    "SAI": {
        "number": "55",
        "name": "Carlos Sainz",
        "nationality": "ESP",
        "alpine_seasons": [2017, 2018],
    },
    "VER": {
        "number": "1",
        "name": "Max Verstappen",
        "nationality": "NED",
        "alpine_seasons": [],
    },
    "NOR": {
        "number": "4",
        "name": "Lando Norris",
        "nationality": "GBR",
        "alpine_seasons": [],
    },
    "LEC": {
        "number": "16",
        "name": "Charles Leclerc",
        "nationality": "MON",
        "alpine_seasons": [],
    },
    "HAM": {
        "number": "44",
        "name": "Lewis Hamilton",
        "nationality": "GBR",
        "alpine_seasons": [],
    },
    "RUS": {
        "number": "63",
        "name": "George Russell",
        "nationality": "GBR",
        "alpine_seasons": [],
    },
    "ALB": {
        "number": "23",
        "name": "Alexander Albon",
        "nationality": "THA",
        "alpine_seasons": [],
    },
}


def map_constructor(raw_team_name: str, season: int) -> ConstructorIdentity:
    """Map a raw constructor display string to a season-aware constructor identity.

    Parameters
    ----------
    raw_team_name : str
        Constructor name from session timing or official results.
    season : int
        Championship season.

    Returns
    -------
    ConstructorIdentity
        Standardized constructor identity with brand and Enstone lineage flags.
    """
    clean = str(raw_team_name).strip().lower()

    # Check for Alpine / Renault / Enstone
    if "alpine" in clean:
        return ConstructorIdentity(
            constructor_id="alpine",
            name="BWT Alpine F1 Team",
            season=season,
            is_alpine_branded=True,
            is_enstone_heritage=True,
            heritage_era="Alpine Era (2021-Present)",
        )

    if "renault" in clean:
        # Renault before 2021 is Enstone heritage, but NOT Alpine branded
        is_heritage = season in range(2002, 2012) or season in range(2016, 2021)
        return ConstructorIdentity(
            constructor_id="renault",
            name="Renault DP World F1 Team" if season == 2020 else "Renault F1 Team",
            season=season,
            is_alpine_branded=False,
            is_enstone_heritage=is_heritage,
            heritage_era="Renault Works II (2016-2020)" if season >= 2016 else "Renault Works I",
        )

    if "lotus" in clean and season in range(2012, 2016):
        return ConstructorIdentity(
            constructor_id="lotus",
            name="Lotus F1 Team",
            season=season,
            is_alpine_branded=False,
            is_enstone_heritage=True,
            heritage_era="Lotus F1 Era (2012-2015)",
        )

    # Competitor constructors
    if "red bull" in clean or "red_bull" in clean:
        return ConstructorIdentity("red_bull", "Oracle Red Bull Racing", season, False, False, "")
    if "ferrari" in clean:
        return ConstructorIdentity("ferrari", "Scuderia Ferrari", season, False, False, "")
    if "mercedes" in clean:
        return ConstructorIdentity(
            "mercedes", "Mercedes-AMG PETRONAS F1 Team", season, False, False, ""
        )
    if "mclaren" in clean:
        return ConstructorIdentity("mclaren", "McLaren F1 Team", season, False, False, "")
    if "aston" in clean:
        return ConstructorIdentity(
            "aston_martin", "Aston Martin Aramco F1 Team", season, False, False, ""
        )
    if "williams" in clean:
        return ConstructorIdentity("williams", "Williams Racing", season, False, False, "")
    if "haas" in clean:
        return ConstructorIdentity("haas", "MoneyGram Haas F1 Team", season, False, False, "")
    if "sauber" in clean or "alfa romeo" in clean or "kick" in clean or "stake" in clean:
        return ConstructorIdentity("sauber", "Stake F1 Team Kick Sauber", season, False, False, "")
    if "audi" in clean:
        return ConstructorIdentity("audi", "Audi F1 Team", season, False, False, "")
    if "toro rosso" in clean or "alphatauri" in clean or "rb" in clean or "racing bulls" in clean:
        return ConstructorIdentity("rb", "Visa Cash App RB", season, False, False, "")
    if "racing point" in clean or "force india" in clean:
        return ConstructorIdentity("racing_point", "Racing Point F1 Team", season, False, False, "")

    # Default fallback for unrecognized constructors
    slug = clean.replace(" ", "_")[:20]
    return ConstructorIdentity(slug, raw_team_name, season, False, False, "")


def map_driver(raw_code_or_name: str, season: int | None = None) -> DriverIdentity:
    """Map driver code or name to a stable DriverIdentity.

    Parameters
    ----------
    raw_code_or_name : str
        Three-letter code (e.g. 'GAS') or driver name.
    season : int or None
        Optional season to verify active Alpine affiliation.

    Returns
    -------
    DriverIdentity
        Resolved driver identity.
    """
    clean = str(raw_code_or_name).strip().upper()
    code = clean[:3]

    if code in KNOWN_DRIVERS:
        info = KNOWN_DRIVERS[code]
        is_alp = (season in info["alpine_seasons"]) if season else len(info["alpine_seasons"]) > 0
        return DriverIdentity(
            driver_code=code,
            driver_number=info["number"],
            full_name=info["name"],
            nationality=info["nationality"],
            is_alpine_driver=is_alp,
        )

    # Search by surname match
    clean_lower = clean.lower()
    for c, info in KNOWN_DRIVERS.items():
        if info["name"].lower() in clean_lower or clean_lower in info["name"].lower():
            is_alp = (
                (season in info["alpine_seasons"]) if season else len(info["alpine_seasons"]) > 0
            )
            return DriverIdentity(
                driver_code=c,
                driver_number=info["number"],
                full_name=info["name"],
                nationality=info["nationality"],
                is_alpine_driver=is_alp,
            )

    return DriverIdentity(
        driver_code=code,
        driver_number="0",
        full_name=raw_code_or_name,
        nationality="UNK",
        is_alpine_driver=False,
    )


def get_season_rivals(season: int) -> list[str]:
    """Retrieve dynamic rival constructor IDs for a given season.

    Parameters
    ----------
    season : int
        Championship year.

    Returns
    -------
    list[str]
        List of rival constructor IDs.
    """
    return SEASON_RIVALS.get(season, ["mclaren", "aston_martin", "haas", "williams"])


def get_alpine_drivers_for_season(season: int) -> list[str]:
    """Get stable driver codes representing Alpine/Renault for a given season.

    Parameters
    ----------
    season : int
        Championship season.

    Returns
    -------
    list[str]
        List of 3-letter driver codes.
    """
    drivers = [
        code for code, info in KNOWN_DRIVERS.items() if season in info.get("alpine_seasons", [])
    ]
    return sorted(drivers)
