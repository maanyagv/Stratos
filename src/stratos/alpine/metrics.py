"""Formula 1 performance analysis metrics calculation module.

Computes clean-lap pace, normalized pace across circuits, sector performance,
speed trap metrics, teammate deltas, tyre degradation slopes, and reliability stats.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


def _get_clean_mask(df: pd.DataFrame) -> pd.Series:
    """Return a boolean Series selecting clean laps."""
    if "is_clean_lap" in df.columns:
        return df["is_clean_lap"].fillna(True).astype(bool)
    return pd.Series(True, index=df.index)


def calculate_clean_lap_pace(laps_df: pd.DataFrame) -> dict[str, Any]:
    """Calculate median clean-lap pace and pace distribution per driver and team.

    Parameters
    ----------
    laps_df : pd.DataFrame
        Laps DataFrame containing 'lap_time_seconds', 'driver', 'team', 'is_clean_lap'.

    Returns
    -------
    dict[str, Any]
        Dictionary with 'drivers' and 'teams' pace summaries.
    """
    if laps_df.empty or "lap_time_seconds" not in laps_df.columns:
        return {"drivers": {}, "teams": {}, "field_median": None}

    clean_mask = _get_clean_mask(laps_df)
    has_time = laps_df["lap_time_seconds"].notna() & (laps_df["lap_time_seconds"] > 0)
    valid_laps = laps_df[clean_mask & has_time]

    if valid_laps.empty:
        return {"drivers": {}, "teams": {}, "field_median": None}

    field_median = float(valid_laps["lap_time_seconds"].median())

    drivers_pace: dict[str, dict[str, Any]] = {}
    if "driver" in valid_laps.columns:
        for driver, grp in valid_laps.groupby("driver"):
            times = grp["lap_time_seconds"].dropna().values
            if len(times) == 0:
                continue
            drivers_pace[str(driver)] = {
                "median_pace": round(float(np.median(times)), 3),
                "mean_pace": round(float(np.mean(times)), 3),
                "std_pace": round(float(np.std(times)), 3),
                "p25_pace": round(float(np.percentile(times, 25)), 3),
                "p75_pace": round(float(np.percentile(times, 75)), 3),
                "clean_laps_count": int(len(times)),
                "delta_to_field_median": round(float(np.median(times) - field_median), 3),
            }

    teams_pace: dict[str, dict[str, Any]] = {}
    if "team" in valid_laps.columns:
        for team, grp in valid_laps.groupby("team"):
            times = grp["lap_time_seconds"].dropna().values
            if len(times) == 0:
                continue
            teams_pace[str(team)] = {
                "median_pace": round(float(np.median(times)), 3),
                "mean_pace": round(float(np.mean(times)), 3),
                "std_pace": round(float(np.std(times)), 3),
                "clean_laps_count": int(len(times)),
                "delta_to_field_median": round(float(np.median(times) - field_median), 3),
            }

    return {
        "field_median": round(field_median, 3),
        "drivers": drivers_pace,
        "teams": teams_pace,
    }


def calculate_normalized_pace(
    laps_df: pd.DataFrame, reference_method: str = "field_median"
) -> pd.DataFrame:
    """Normalize lap times to percentage delta relative to session reference.

    Normalizing lap times to percentage deltas enables valid performance comparisons
    across different tracks (e.g. Monaco vs Monza) without lap distance distortion.

    Parameters
    ----------
    laps_df : pd.DataFrame
        Laps DataFrame.
    reference_method : str, default 'field_median'
        'field_median' or 'fastest_clean_lap'.

    Returns
    -------
    pd.DataFrame
        DataFrame with added 'normalized_pace_delta_pct' column.
    """
    if laps_df.empty or "lap_time_seconds" not in laps_df.columns:
        return laps_df.copy()

    clean_mask = _get_clean_mask(laps_df)
    has_time = laps_df["lap_time_seconds"].notna() & (laps_df["lap_time_seconds"] > 0)
    valid_times = laps_df.loc[clean_mask & has_time, "lap_time_seconds"]

    if valid_times.empty:
        df_out = laps_df.copy()
        df_out["normalized_pace_delta_pct"] = np.nan
        return df_out

    if reference_method == "fastest_clean_lap":
        ref_time = float(valid_times.min())
    else:
        ref_time = float(valid_times.median())

    df_out = laps_df.copy()
    df_out["normalized_pace_delta_pct"] = (
        (df_out["lap_time_seconds"] / ref_time) - 1.0
    ) * 100.0

    return df_out


def calculate_sector_performance(laps_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Compute median clean sector times and sector speed ranks.

    Parameters
    ----------
    laps_df : pd.DataFrame
        Laps DataFrame with 'sector_1_seconds', 'sector_2_seconds', 'sector_3_seconds'.

    Returns
    -------
    dict[str, dict[str, float]]
        Median sector times per constructor or driver.
    """
    if laps_df.empty:
        return {}

    clean_laps = laps_df[_get_clean_mask(laps_df)]
    entity_col = "team" if "team" in clean_laps.columns else "driver"
    if entity_col not in clean_laps.columns:
        return {}

    sector_results: dict[str, dict[str, float]] = {}
    for entity, grp in clean_laps.groupby(entity_col):
        s1 = grp["sector_1_seconds"].dropna().values if "sector_1_seconds" in grp.columns else []
        s2 = grp["sector_2_seconds"].dropna().values if "sector_2_seconds" in grp.columns else []
        s3 = grp["sector_3_seconds"].dropna().values if "sector_3_seconds" in grp.columns else []

        sector_results[str(entity)] = {
            "sector_1_median": round(float(np.median(s1)), 3) if len(s1) > 0 else 0.0,
            "sector_2_median": round(float(np.median(s2)), 3) if len(s2) > 0 else 0.0,
            "sector_3_median": round(float(np.median(s3)), 3) if len(s3) > 0 else 0.0,
        }

    return sector_results


def calculate_speed_trap_performance(laps_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Calculate maximum and median clean speeds at timing traps.

    Parameters
    ----------
    laps_df : pd.DataFrame
        Laps DataFrame with 'speed_st', 'speed_fl', 'speed_i1', 'speed_i2'.

    Returns
    -------
    dict[str, dict[str, float]]
        Speed trap statistics per entity.
    """
    if laps_df.empty:
        return {}

    entity_col = "team" if "team" in laps_df.columns else "driver"
    if entity_col not in laps_df.columns:
        return {}

    speed_cols = ["speed_st", "speed_fl", "speed_i1", "speed_i2"]
    results: dict[str, dict[str, float]] = {}

    for entity, grp in laps_df.groupby(entity_col):
        res: dict[str, float] = {}
        for sc in speed_cols:
            if sc in grp.columns:
                valid = grp[sc].dropna().astype(float).values
                if len(valid) > 0:
                    res[f"{sc}_max"] = round(float(np.max(valid)), 1)
                    res[f"{sc}_median"] = round(float(np.median(valid)), 1)
                else:
                    res[f"{sc}_max"] = 0.0
                    res[f"{sc}_median"] = 0.0
        results[str(entity)] = res

    return results


def calculate_qualifying_performance(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate qualifying pace relative to pole position and field baseline.

    Parameters
    ----------
    results : list[dict[str, Any]]
        List of driver result dictionaries from qualifying session.

    Returns
    -------
    dict[str, Any]
        Pole time, driver deltas, and constructor average deltas.
    """
    if not results:
        return {"pole_time": None, "drivers": {}, "constructors": {}}

    driver_best_times: dict[str, float] = {}
    driver_info: dict[str, dict[str, Any]] = {}

    for r in results:
        code = r["driver_code"]
        cand_times = [
            r.get("q3_time"),
            r.get("q2_time"),
            r.get("q1_time"),
            r.get("fastest_lap_time"),
        ]
        times = [t for t in cand_times if t is not None and float(t) > 0]
        if times:
            driver_best_times[code] = min(times)
            driver_info[code] = r

    if not driver_best_times:
        return {"pole_time": None, "drivers": {}, "constructors": {}}

    pole_time = min(driver_best_times.values())
    driver_deltas: dict[str, dict[str, Any]] = {}
    constructor_deltas_raw: dict[str, list[float]] = {}

    for code, best_t in driver_best_times.items():
        delta_sec = best_t - pole_time
        delta_pct = (delta_sec / pole_time) * 100.0
        c_id = driver_info[code].get("constructor_id", "unknown")

        driver_deltas[code] = {
            "driver_name": driver_info[code].get("driver_name", code),
            "constructor_id": c_id,
            "best_time": round(best_t, 3),
            "delta_seconds": round(delta_sec, 3),
            "delta_pct": round(delta_pct, 3),
            "grid_position": driver_info[code].get("grid_position"),
        }

        constructor_deltas_raw.setdefault(c_id, []).append(delta_pct)

    constructor_deltas: dict[str, dict[str, float]] = {}
    for c_id, deltas in constructor_deltas_raw.items():
        constructor_deltas[c_id] = {
            "mean_delta_pct": round(float(np.mean(deltas)), 3),
            "min_delta_pct": round(float(np.min(deltas)), 3),
        }

    return {
        "pole_time": round(pole_time, 3),
        "drivers": driver_deltas,
        "constructors": constructor_deltas,
    }


def calculate_teammate_comparison(
    laps_df: pd.DataFrame,
    results: list[dict[str, Any]],
    constructor_id: str = "alpine",
) -> dict[str, Any]:
    """Calculate intra-team qualifying and race-pace difference between teammates.

    Parameters
    ----------
    laps_df : pd.DataFrame
        Session laps DataFrame.
    results : list[dict[str, Any]]
        Driver classifications.
    constructor_id : str, default 'alpine'
        Target constructor key.

    Returns
    -------
    dict[str, Any]
        Teammate comparison metrics.
    """
    team_results = [r for r in results if r.get("constructor_id") == constructor_id]
    if len(team_results) < 2:
        codes = [r["driver_code"] for r in team_results]
        return {"status": "INSUFFICIENT_DRIVERS", "drivers": codes}

    d1, d2 = team_results[0], team_results[1]
    c1, c2 = d1["driver_code"], d2["driver_code"]

    # Qualifying delta
    q1_t = d1.get("fastest_lap_time") or d1.get("q3_time") or d1.get("q1_time")
    q2_t = d2.get("fastest_lap_time") or d2.get("q3_time") or d2.get("q1_time")
    qualy_delta = round(float(q1_t - q2_t), 3) if (q1_t and q2_t) else None

    # Clean race pace comparison
    race_delta = None
    if not laps_df.empty and "lap_time_seconds" in laps_df.columns and "driver" in laps_df.columns:
        mask = _get_clean_mask(laps_df)
        t1 = laps_df[mask & (laps_df["driver"] == c1)]["lap_time_seconds"].dropna().values
        t2 = laps_df[mask & (laps_df["driver"] == c2)]["lap_time_seconds"].dropna().values
        if len(t1) > 0 and len(t2) > 0:
            race_delta = round(float(np.median(t1) - np.median(t2)), 3)

    # Finishing positions and points
    fin_delta = None
    if d1.get("finish_position") and d2.get("finish_position"):
        fin_delta = int(d1["finish_position"]) - int(d2["finish_position"])

    pts_delta = round(float(d1.get("points", 0.0) - d2.get("points", 0.0)), 1)

    return {
        "constructor_id": constructor_id,
        "driver_1": c1,
        "driver_2": c2,
        "driver_1_name": d1.get("driver_name", c1),
        "driver_2_name": d2.get("driver_name", c2),
        "qualifying_delta_seconds": qualy_delta,  # negative means d1 was faster
        "race_clean_pace_delta_seconds": race_delta,  # negative means d1 was faster
        "finish_position_delta": fin_delta,  # negative means d1 finished ahead
        "points_delta": pts_delta,  # positive means d1 scored more
    }


def calculate_tyre_degradation(
    laps_df: pd.DataFrame, fuel_correction_per_lap: float = 0.033
) -> dict[str, dict[str, Any]]:
    """Compute fuel-corrected tyre degradation slopes (s/lap) per compound.

    Parameters
    ----------
    laps_df : pd.DataFrame
        Laps DataFrame with 'lap_time_seconds', 'tyre_life', 'compound', 'lap_number'.
    fuel_correction_per_lap : float, default 0.033
        Fuel mass burn correction (seconds saved per lap due to lightening fuel load).

    Returns
    -------
    dict[str, dict[str, Any]]
        Compound degradation slopes, intercepts, and R^2 values.
    """
    required_cols = {"lap_time_seconds", "tyre_life", "compound", "lap_number"}
    if laps_df.empty or not required_cols.issubset(laps_df.columns):
        return {}

    mask = _get_clean_mask(laps_df)
    has_time = laps_df["lap_time_seconds"].notna() & (laps_df["tyre_life"] > 0)
    valid_laps = laps_df[mask & has_time].copy()

    if valid_laps.empty:
        return {}

    valid_laps["fuel_corrected_time"] = (
        valid_laps["lap_time_seconds"] + (valid_laps["lap_number"] - 1) * fuel_correction_per_lap
    )

    results: dict[str, dict[str, Any]] = {}
    for compound, grp in valid_laps.groupby("compound"):
        comp_str = str(compound).upper().strip()
        if comp_str in {"UNKNOWN", "NAN"}:
            continue

        x = grp["tyre_life"].values.astype(float)
        y = grp["fuel_corrected_time"].values.astype(float)

        if len(x) < 4:
            continue

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        results[comp_str] = {
            "degradation_rate_sec_per_lap": round(float(slope), 4),
            "base_lap_time": round(float(intercept), 3),
            "r_squared": round(float(r_value**2), 3),
            "sample_laps": int(len(x)),
            "max_tyre_life": int(np.max(x)),
        }

    return results


def calculate_pit_performance(pit_stops: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate operational pit stop duration and pit lane time loss.

    Parameters
    ----------
    pit_stops : list[dict[str, Any]]
        List of pit stop records with 'pit_duration' and 'pit_lane_time'.

    Returns
    -------
    dict[str, Any]
        Summary metrics for stationary and total transit times.
    """
    if not pit_stops:
        return {
            "total_stops": 0,
            "stationary_median": None,
            "stationary_min": None,
            "pit_lane_loss_median": None,
        }

    stationary_times = [
        float(ps["pit_duration"])
        for ps in pit_stops
        if ps.get("pit_duration") is not None and float(ps["pit_duration"]) > 0
    ]
    lane_times = [
        float(ps["pit_lane_time"])
        for ps in pit_stops
        if ps.get("pit_lane_time") is not None and float(ps["pit_lane_time"]) > 0
    ]

    stat_med = round(float(np.median(stationary_times)), 2) if stationary_times else None
    stat_min = round(float(np.min(stationary_times)), 2) if stationary_times else None
    stat_std = (
        round(float(np.std(stationary_times)), 2)
        if len(stationary_times) > 1
        else 0.0
    )
    lane_med = round(float(np.median(lane_times)), 2) if lane_times else None
    lane_min = round(float(np.min(lane_times)), 2) if lane_times else None

    return {
        "total_stops": len(pit_stops),
        "stationary_median": stat_med,
        "stationary_min": stat_min,
        "stationary_std": stat_std,
        "pit_lane_loss_median": lane_med,
        "pit_lane_loss_min": lane_min,
    }


def calculate_reliability_stats(
    results_df: pd.DataFrame, constructor_id: str = "alpine"
) -> dict[str, Any]:
    """Compute finishing, reliability, retirement, and points statistics.

    Parameters
    ----------
    results_df : pd.DataFrame
        DataFrame of session results with 'constructor_id', 'finish_status', 'points'.
    constructor_id : str, default 'alpine'
        Target constructor key.

    Returns
    -------
    dict[str, Any]
        Reliability summary.
    """
    if results_df.empty or "constructor_id" not in results_df.columns:
        return {
            "total_starts": 0,
            "classified_finishes": 0,
            "classified_rate_pct": 0.0,
            "mechanical_dnfs": 0,
            "collision_dnfs": 0,
            "total_points": 0.0,
            "points_per_start": 0.0,
        }

    team_data = results_df[results_df["constructor_id"] == constructor_id]
    total_starts = len(team_data)
    if total_starts == 0:
        return {
            "total_starts": 0,
            "classified_finishes": 0,
            "classified_rate_pct": 0.0,
            "mechanical_dnfs": 0,
            "collision_dnfs": 0,
            "total_points": 0.0,
            "points_per_start": 0.0,
        }

    status_series = team_data["finish_status"].fillna("Finished").str.lower()
    is_classified = status_series.str.contains("finished") | status_series.str.contains(r"\+\d")
    classified_count = int(is_classified.sum())

    dnf_data = team_data[~is_classified]
    mech_keywords = [
        "engine", "power", "hydraulics", "gearbox", "brake",
        "electrical", "mechanical", "oil", "water",
    ]
    mech_count = 0
    collision_count = 0
    for _, row in dnf_data.iterrows():
        s = str(row.get("finish_status", "")).lower()
        if any(k in s for k in mech_keywords):
            mech_count += 1
        elif "collision" in s or "accident" in s or "damage" in s or "spins" in s:
            collision_count += 1
        else:
            mech_count += 1

    total_pts = float(team_data["points"].fillna(0.0).sum())

    return {
        "total_starts": total_starts,
        "classified_finishes": classified_count,
        "classified_rate_pct": round((classified_count / total_starts) * 100.0, 1),
        "mechanical_dnfs": mech_count,
        "collision_dnfs": collision_count,
        "total_points": round(total_pts, 1),
        "points_per_start": round(total_pts / total_starts, 2),
    }
