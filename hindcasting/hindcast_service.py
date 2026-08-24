"""
Hindcast service - identical core physics to hindcasting.py, but
fetch_current/fetch_wind now read from the 14 pre-fetched real
Open-Meteo records (hindcast_env_seed.json) instead of a static
constant or synthetic grid.

Determinism: given the same observation_time, this ALWAYS returns the
same record - no randomness at call time. Matching is done by nearest
hour-of-day (not nearest absolute date), because the 14 seed records
only span ~44 real hours (2026-08-24/25), while requested spills can
be from any date (e.g. a 2020 test image). Matching by absolute date
distance would be meaningless across that gap; matching by hour-of-day
treats the sample as "roughly what conditions look like at this time
of day in this region" - the honest way to reuse a small real sample
across arbitrary dates.

Position: observed_position (lat/lon) is passed straight through from
HindcastInput - it may originate from DetectionOutput.centroid via the
orchestrator, or be supplied directly (e.g. by the frontend for manual
testing). This module doesn't care where it came from. It IS used for
the actual drift-walk math (destination_point). It is NOT used to
spatially match the environmental lookup - the 14 seed records were
fetched for one representative region only, so environmental data is
matched by time-of-day alone, not by proximity to the requested
position. This is a disclosed simplification: results are only
representative if the requested spill is near that sampled region.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from data.schemas import (
    EnvironmentSource,
    EnvironmentVector,
    HindcastInput,
    HindcastModelParams,
    HindcastOutput,
    LatLon,
    TimedPoint,
)

EARTH_RADIUS_KM = 6371.0

DEFAULT_ENV_SOURCE = EnvironmentSource.cached_live_sample

_SEED_DATA_PATH = Path(__file__).parent / "hindcast_data.json"
_seed_records_cache: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Seed data loading + deterministic nearest-hour-of-day matching
# ---------------------------------------------------------------------------

def _load_seed_records() -> list[dict[str, Any]]:
    global _seed_records_cache

    if _seed_records_cache is None:

        if not _SEED_DATA_PATH.exists():
            raise FileNotFoundError(
                f"{_SEED_DATA_PATH} not found - "
                "run seeding_hindcast_data.py first"
            )

        with open(
            _SEED_DATA_PATH,
            "r",
            encoding="utf-8"
        ) as f:
            _seed_records_cache = json.load(f)

    if _seed_records_cache is None:
        raise RuntimeError(
            "Seed records could not be loaded"
        )

    return _seed_records_cache


def _hour_of_day_distance(a_hour: float, b_hour: float) -> float:
    """Circular distance between two hour-of-day values (0-24), so
    23:00 and 01:00 are correctly treated as 2 hours apart, not 22."""
    diff = abs(a_hour - b_hour) % 24
    return min(diff, 24 - diff)


def _nearest_seed_record(time: datetime) -> dict[str, Any]:
    """Deterministic: the same `time` always returns the same record.
    No randomness, no call-order dependence.
    """

    records = _load_seed_records()

    if not records:
        raise ValueError(
            "No seed records are available."
        )

    target_hour = (
        time.hour +
        time.minute / 60.0
    )

    best: dict[str, Any] | None = None
    best_dist = float("inf")

    for r in records:

        r_time = datetime.fromisoformat(
            r["data_timestamp"].replace(
                "Z",
                "+00:00"
            )
        )

        r_hour = (
            r_time.hour +
            r_time.minute / 60.0
        )

        dist = _hour_of_day_distance(
            target_hour,
            r_hour
        )

        if dist < best_dist:
            best = r
            best_dist = dist

    if best is None:
        raise RuntimeError(
            "Unable to find a nearest seed record."
        )

    return best


def fetch_current(position: LatLon, time: datetime) -> EnvironmentVector:
    """position is accepted for interface consistency with the other
    source modes (static_sample/synthetic_dataset/live_api all take
    it too) but is NOT used for matching here - see module docstring."""
    r = _nearest_seed_record(time)
    return EnvironmentVector(
        speed_kmh=r["current"]["speed_kmh"],
        direction_deg=r["current"]["direction_deg"],
        source=EnvironmentSource.cached_live_sample,
        data_timestamp=datetime.fromisoformat(r["data_timestamp"].replace("Z", "+00:00")),
    )


def fetch_wind(position: LatLon, time: datetime) -> EnvironmentVector:
    r = _nearest_seed_record(time)
    return EnvironmentVector(
        speed_kmh=r["wind"]["speed_kmh"],
        direction_deg=r["wind"]["direction_deg"],
        source=EnvironmentSource.cached_live_sample,
        data_timestamp=datetime.fromisoformat(r["data_timestamp"].replace("Z", "+00:00")),
    )


# ---------------------------------------------------------------------------
# Core vector math - unchanged from hindcasting.py
# ---------------------------------------------------------------------------

def destination_point(lat: float, lon: float, distance_km: float, bearing_deg: float) -> tuple[float, float]:
    """
    Move a point along the Earth's surface by distance_km at bearing_deg
    (0 = north, 90 = east, 180 = south, 270 = west). Great-circle
    (haversine-based) calculation.
    """
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    bearing = math.radians(bearing_deg)
    angular_distance = distance_km / EARTH_RADIUS_KM

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    lon2_deg = math.degrees(lon2)
    lon2_deg = ((lon2_deg + 180) % 360) - 180
    return math.degrees(lat2), lon2_deg


def _vector_components(speed_kmh: float, direction_deg: float) -> tuple[float, float]:
    direction = math.radians(direction_deg)
    return speed_kmh * math.cos(direction), speed_kmh * math.sin(direction)


def combine_environment(
    current: EnvironmentVector,
    wind: EnvironmentVector,
    windage_coefficient: float,
) -> tuple[float, float]:
    current_north, current_east = _vector_components(current.speed_kmh, current.direction_deg)
    wind_north, wind_east = _vector_components(wind.speed_kmh, wind.direction_deg)

    north = current_north + windage_coefficient * wind_north
    east = current_east + windage_coefficient * wind_east

    speed = math.sqrt(north ** 2 + east ** 2)
    bearing = (math.degrees(math.atan2(east, north)) + 360) % 360
    return speed, bearing


def _walk_path(
    start_lat: float,
    start_lon: float,
    start_time: datetime,
    drift_speed_kmh: float,
    drift_bearing_deg: float,
    timestep_minutes: int,
    total_hours: int,
    direction: str,
) -> list[TimedPoint]:
    if direction not in ("backward", "forward"):
        raise ValueError("direction must be 'backward' or 'forward'")

    sign = -1 if direction == "backward" else 1
    bearing = (drift_bearing_deg + 180) % 360 if direction == "backward" else drift_bearing_deg
    step_hours = timestep_minutes / 60.0
    num_steps = int(total_hours / step_hours)

    path: list[TimedPoint] = []
    lat, lon = start_lat, start_lon
    t = start_time

    for _ in range(num_steps):
        distance_km = drift_speed_kmh * step_hours
        lat, lon = destination_point(lat, lon, distance_km, bearing)
        t = t + sign * timedelta(hours=step_hours)
        path.append(TimedPoint(lat=lat, lon=lon, t=t))

    return path


# ---------------------------------------------------------------------------
# Orchestrator - same signature/contract as hindcasting.py's run_hindcast
# ---------------------------------------------------------------------------

def run_hindcast(
    hindcast_input: HindcastInput,
    env_source: EnvironmentSource = DEFAULT_ENV_SOURCE,
) -> HindcastOutput:
    position = hindcast_input.observed_position
    obs_time = hindcast_input.observation_time

    if env_source != EnvironmentSource.cached_live_sample:
        raise NotImplementedError(
            f"hindcast_service.py only implements cached_live_sample - "
            f"got {env_source}. Use hindcasting.py for static_sample/"
            f"synthetic_dataset/live_api."
        )

    current = fetch_current(position, obs_time)
    wind = fetch_wind(position, obs_time)

    params = HindcastModelParams()
    drift_speed, drift_bearing = combine_environment(current, wind, params.windage_coefficient)

    backward_path = _walk_path(
        position.lat, position.lon, obs_time,
        drift_speed, drift_bearing,
        params.timestep_minutes, params.lookback_hours,
        direction="backward",
    )
    forward_path = _walk_path(
        position.lat, position.lon, obs_time,
        drift_speed, drift_bearing,
        params.timestep_minutes, params.lookahead_hours,
        direction="forward",
    )

    origin_estimate = (
        backward_path[-1] if backward_path
        else TimedPoint(lat=position.lat, lon=position.lon, t=obs_time)
    )

    return HindcastOutput(
        spill_id=hindcast_input.spill_id,
        origin_estimate=origin_estimate,
        backward_path=backward_path,
        forward_path=forward_path,
        current_input=current,
        wind_input=wind,
        model_params=params,
        model_notes=(
            "Single representative current/wind vector, deterministic single "
            "path - not a spatially-varying field or ensemble. Environmental "
            "values are real measurements (Open-Meteo) fetched once for one "
            "representative region and matched to the request by nearest "
            "hour-of-day, not by date or by proximity to the requested "
            "position - representative only if the spill is near that region."
        ),
    )


if __name__ == "__main__":
    sample_input = HindcastInput(
        spill_id="demo-spill-1",
        observed_position=LatLon(lat=28.78874, lon=-89.25681),
        observation_time=datetime(2020, 3, 6, 3, 0, 0),  # historical date, arbitrary hour
    )
    result = run_hindcast(sample_input)
    print(result.model_dump_json(indent=2))