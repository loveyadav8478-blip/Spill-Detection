"""
Hindcasting / drift module.

Pay attention to the data ingestion whether to get it from and api or hard code it etc
Fetching environmental data (current + wind) and running the vector-based backward/forward drift simulation.
- Detection only ever hands over spill_id + observed_position + observation_time.

Flow (locked):
  1. Ingest HindcastInput from detection
  2. Fetch env factors (current, wind) - internal to this module
  3. Load model_params - fixed constants, not calculated per-request
  4. Run vector algorithm (backward AND forward)
  5. Return HindcastOutput

No ML here - this is deterministic vector physics (great-circle
destination point + windage-weighted drift), the same class of
approach real tools like NOAA GNOME use, just simplified:
  - one representative current/wind vector for the whole window,
    not a spatially-varying field
  - one deterministic path, not a Monte Carlo ensemble
Both simplifications are stated explicitly in the output via
`is_simplified_model` / `model_notes`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..data.schemas import (
    EnvironmentVector,
    HindcastInput,
    HindcastModelParams,
    HindcastOutput,
    LatLon,
    TimedPoint,
)

EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Environmental data fetch - static sample lookups for the prototype.
# Swap these two functions for real API calls (HYCOM/OSCAR for current,
# GFS/ERA5 for wind) post-hackathon. Nothing else in this file needs to
# change when that happens - they're the only functions that touch an
# external data source.
# ---------------------------------------------------------------------------

def fetch_current(position: LatLon, time: datetime) -> EnvironmentVector:
    """Static sample current vector for the prototype."""
    return EnvironmentVector(
        speed_kmh=1.4,
        direction_deg=210.0,
        source="static_sample",
        data_timestamp=time,
    )


def fetch_wind(position: LatLon, time: datetime) -> EnvironmentVector:
    """Static sample wind vector for the prototype.
    #imp -> for weather apis check the vector formatting
    """
    return EnvironmentVector(
        speed_kmh=22.3,
        direction_deg=195.0,
        source="static_sample",
        data_timestamp=time,
    )


# ---------------------------------------------------------------------------
# Core vector math
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

    return math.degrees(lat2), math.degrees(lon2)


def _vector_components(speed_kmh: float, direction_deg: float) -> tuple[float, float]:
    """Convert speed + bearing into north/east components (km/h each)."""
    direction = math.radians(direction_deg)
    north = speed_kmh * math.cos(direction)
    east = speed_kmh * math.sin(direction)
    return north, east


def combine_environment(
    current: EnvironmentVector,
    wind: EnvironmentVector,
    windage_coefficient: float,
) -> tuple[float, float]:
    """
    Combine wind and current into one net surface-drift vector.
    Only a fraction of wind speed (windage_coefficient) transfers to
    floating oil via surface drag; current transfers at full weight.
    Returns (speed_kmh, direction_deg) of the combined drift.
    """
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
    """
    Walk a path forward or backward from the start point, one timestep
    at a time. 'backward' reverses the bearing 180deg (same drift
    vector, opposite direction) and steps time backward; 'forward' uses
    the bearing as-is and steps time forward.
    """
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
# Orchestrator - this is the function the API layer calls
# ---------------------------------------------------------------------------

def run_hindcast(hindcast_input: HindcastInput) -> HindcastOutput:
    """
    Full hindcast pipeline for one spill: fetch env data, load fixed
    model params, run backward + forward vector walk, return the
    complete HindcastOutput matching the locked schema.
    """
    position = hindcast_input.observed_position
    obs_time = hindcast_input.observation_time

    # Step 2: fetch env factors
    current = fetch_current(position, obs_time)
    wind = fetch_wind(position, obs_time)

    # Step 3: load fixed model params (not calculated per-request)
    params = HindcastModelParams()

    # Step 4: run vector algorithm, both directions
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

    # Step 5: package output
    return HindcastOutput(
        spill_id=hindcast_input.spill_id,
        origin_estimate=origin_estimate,
        backward_path=backward_path,
        forward_path=forward_path,
        current_input=current,
        wind_input=wind,
        model_params=params,
    )


if __name__ == "__main__":
    # Quick manual smoke test - not part of the API flow.
    sample_input = HindcastInput(
        spill_id="demo-spill-1",
        observed_position=LatLon(lat=28.78874, lon=-89.25681),
        observation_time=datetime(2020, 3, 6, 0, 0, 0),
    )
    result = run_hindcast(sample_input)
    print(result.model_dump_json(indent=2))