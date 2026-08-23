"""
Basic FastAPI entrypoint wiring the full pipeline:
detection -> hindcast -> AIS filter -> AIS score -> dashboard

Each stage is implemented as a plain function (not a network call) so the
whole pipeline runs in-process for the prototype - matches the "modular
monolith, not distributed microservices" plan.

Run with:  uvicorn main:app --reload
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timedelta

from ais_analysis.pipeline import run_ais_pipeline

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, Form
from PIL import Image
from shapely.geometry import Point, LineString

from data.schemas import (
    DetectionOutput,
    GeoJSONPolygon,
    HindcastInput,
    HindcastOutput,
    HindcastModelParams,
    EnvironmentVector,
    TimedPoint,
    LatLon,
    AISPing,
    AISFilterInput,
    AISScoreOutput,
    ScoredVessel,
    AnomalyFlags,
    DashboardResponse,
)

app = FastAPI(title="Oil Spill Detection & Attribution API")

EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Stage 1: Detection
# ---------------------------------------------------------------------------

def run_detection(
    spill_id: str,
    mask_bytes: bytes,
    top_left_lat: float,
    top_left_lon: float,
    pixel_size_deg: float,
    image_timestamp: datetime,
) -> DetectionOutput:
    """
    Extracts a polygon from a binary mask image and converts pixel
    coordinates to real lat/lon using a simple flat geotransform.
    Confidence is a stub (mask coverage ratio) until a real model
    confidence score is wired in.
    """
    mask_img = np.array(Image.open(io.BytesIO(mask_bytes)).convert("L"))
    _, binary = cv2.threshold(mask_img, 127, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        raise ValueError("No spill contour found in mask image")

    largest = max(contours, key=cv2.contourArea)

    def px_to_latlon(px, py):
        lat = top_left_lat - (py * pixel_size_deg)
        lon = top_left_lon + (px * pixel_size_deg)
        return lon, lat  # GeoJSON order: [lon, lat]

    ring = [px_to_latlon(pt[0][0], pt[0][1]) for pt in largest]
    ring.append(ring[0])  # close the polygon

    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    centroid_lon = sum(lons) / len(lons)
    centroid_lat = sum(lats) / len(lats)

    # rough area/perimeter in km using a flat-earth approximation near centroid
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(centroid_lat))
    area_px = cv2.contourArea(largest)
    area_km2 = area_px * (pixel_size_deg * km_per_deg_lat) * (pixel_size_deg * km_per_deg_lon)
    perimeter_px = cv2.arcLength(largest, closed=True)
    perimeter_km = perimeter_px * pixel_size_deg * ((km_per_deg_lat + km_per_deg_lon) / 2)

    mask_coverage = float(np.count_nonzero(binary)) / binary.size
    confidence_score = min(1.0, max(0.0, mask_coverage * 5))  # stub heuristic

    return DetectionOutput(
        spill_id=spill_id,
        detected_mask=GeoJSONPolygon(coordinates=[[list(pt) for pt in ring]]),
        area_km2=round(area_km2, 4),
        perimeter_km=round(perimeter_km, 4),
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        detection_timestamp=image_timestamp,
        confidence_score=confidence_score,
    )


# ---------------------------------------------------------------------------
# Stage 2: Hindcast / drift
# ---------------------------------------------------------------------------

def fetch_current(position: LatLon, time: datetime) -> EnvironmentVector:
    """Static sample lookup for the prototype - replace with a real
    current-data source (HYCOM/OSCAR) post-hackathon."""
    return EnvironmentVector(
        speed_kmh=1.4, direction_deg=210.0, source="static_sample", data_timestamp=time
    )


def fetch_wind(position: LatLon, time: datetime) -> EnvironmentVector:
    """Static sample lookup for the prototype - replace with a real
    wind-data source (GFS/ERA5) post-hackathon."""
    return EnvironmentVector(
        speed_kmh=22.3, direction_deg=195.0, source="static_sample", data_timestamp=time
    )


def _destination_point(lat, lon, distance_km, bearing_deg):
    lat1, lon1, bearing = map(math.radians, (lat, lon, bearing_deg))
    ang = distance_km / EARTH_RADIUS_KM
    lat2 = math.asin(math.sin(lat1) * math.cos(ang) + math.cos(lat1) * math.sin(ang) * math.cos(bearing))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(ang) * math.cos(lat1),
        math.cos(ang) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def _net_drift_vector(current: EnvironmentVector, wind: EnvironmentVector, windage: float):
    def components(speed, direction_deg):
        d = math.radians(direction_deg)
        return speed * math.cos(d), speed * math.sin(d)  # north, east

    cn, ce = components(current.speed_kmh, current.direction_deg)
    wn, we = components(wind.speed_kmh, wind.direction_deg)
    north = cn + windage * wn
    east = ce + windage * we
    speed = math.sqrt(north ** 2 + east ** 2)
    bearing = (math.degrees(math.atan2(east, north)) + 360) % 360
    return speed, bearing


def _walk_path(start_lat, start_lon, start_time, speed_kmh, bearing_deg, params, direction):
    """direction: 'backward' or 'forward'. Returns list of TimedPoint,
    ordered from start_time outward."""
    sign = -1 if direction == "backward" else 1
    bearing = (bearing_deg + 180) % 360 if direction == "backward" else bearing_deg
    total_hours = params.lookback_hours if direction == "backward" else params.lookahead_hours
    step_hours = params.timestep_minutes / 60.0

    path = []
    steps = int(total_hours / step_hours)
    lat, lon = start_lat, start_lon
    t = start_time
    for _ in range(steps):
        distance = speed_kmh * step_hours
        lat, lon = _destination_point(lat, lon, distance, bearing)
        t = t + sign * timedelta(hours=step_hours)
        path.append(TimedPoint(lat=lat, lon=lon, t=t))
    return path


def run_hindcast(hindcast_input: HindcastInput) -> HindcastOutput:
    position = hindcast_input.observed_position
    obs_time = hindcast_input.observation_time
    params = HindcastModelParams()  # fixed constants, not calculated per-request

    current = fetch_current(position, obs_time)
    wind = fetch_wind(position, obs_time)
    speed, bearing = _net_drift_vector(current, wind, params.windage_coefficient)

    backward_path = _walk_path(position.lat, position.lon, obs_time, speed, bearing, params, "backward")
    forward_path = _walk_path(position.lat, position.lon, obs_time, speed, bearing, params, "forward")

    origin_estimate = backward_path[-1] if backward_path else TimedPoint(
        lat=position.lat, lon=position.lon, t=obs_time
    )

    return HindcastOutput(
        spill_id=hindcast_input.spill_id,
        origin_estimate=origin_estimate,
        backward_path=backward_path,
        forward_path=forward_path,
        current_input=current,
        wind_input=wind,
        model_params=params,
    )


# ---------------------------------------------------------------------------
# Stage 3 + 4: AIS filtering and scoring (combined - filtering is an
# internal step of the same function, per the locked flow)
# ---------------------------------------------------------------------------

def run_ais_filter_and_score(filter_input: AISFilterInput) -> AISScoreOutput:
    origin_pt = Point(filter_input.origin_estimate.lon, filter_input.origin_estimate.lat)
    backward_line = LineString(
        [(p.lon, p.lat) for p in filter_input.backward_path]
    ) if len(filter_input.backward_path) >= 2 else None

    # group raw pings by vessel
    by_mmsi: dict[str, list[AISPing]] = {}
    for ping in filter_input.raw_ais_pings:
        by_mmsi.setdefault(ping.mmsi, []).append(ping)

    scored: list[ScoredVessel] = []

    for mmsi, pings in by_mmsi.items():
        pings.sort(key=lambda p: p.base_date_time)
        traj_points = [TimedPoint(lat=p.lat, lon=p.lon, t=p.base_date_time) for p in pings]

        # Level 1: coarse filter - proximity + time window
        min_dist_km = min(
            origin_pt.distance(Point(p.lon, p.lat)) * 111.0  # deg -> km, rough
            for p in pings
        )
        min_time_delta_min = min(
            abs((p.base_date_time - filter_input.origin_estimate.t).total_seconds()) / 60.0
            for p in pings
        )
        passed_coarse = (
            min_dist_km < filter_input.coarse_radius_km
            and min_time_delta_min < filter_input.coarse_time_window_hours * 60
        )
        if not passed_coarse:
            continue

        # Level 2: trajectory filter against the backward drift path
        passed_trajectory = True
        if backward_line is not None and len(pings) >= 2:
            vessel_line = LineString([(p.lon, p.lat) for p in pings])
            traj_dist_km = vessel_line.distance(backward_line) * 111.0
            passed_trajectory = traj_dist_km < filter_input.trajectory_max_distance_km

        if not passed_trajectory:
            continue

        # AIS gap detection
        gap_minutes = 0.0
        gap_detected = False
        for a, b in zip(pings, pings[1:]):
            gap = (b.base_date_time - a.base_date_time).total_seconds() / 60.0
            if gap > gap_minutes:
                gap_minutes = gap
        gap_detected = gap_minutes > 30.0

        # crude speed/course deviation scores (stub - no historical baseline yet)
        avg_sog = sum(p.sog for p in pings) / len(pings)
        speed_dev_score = min(1.0, abs(avg_sog - pings[0].sog) / 10.0) if len(pings) > 1 else 0.0
        cogs = [p.cog for p in pings]
        course_dev_score = min(1.0, (max(cogs) - min(cogs)) / 180.0) if len(cogs) > 1 else 0.0

        proximity_score = max(0.0, 1 - min_dist_km / filter_input.coarse_radius_km)
        gap_score = 1.0 if gap_detected else 0.0
        final_score = round(
            0.4 * proximity_score + 0.3 * gap_score + 0.15 * speed_dev_score + 0.15 * course_dev_score,
            4,
        )

        scored.append(
            ScoredVessel(
                mmsi=mmsi,
                vessel_name=pings[0].vessel_name,
                trajectory_points=traj_points,
                min_distance_to_origin_km=round(min_dist_km, 3),
                time_delta_to_origin_min=round(min_time_delta_min, 1),
                anomaly=AnomalyFlags(
                    ais_gap_detected=gap_detected,
                    gap_duration_min=round(gap_minutes, 1),
                    speed_deviation_score=round(speed_dev_score, 3),
                    course_deviation_score=round(course_dev_score, 3),
                ),
                final_suspect_score=final_score,
                rank=0,  # assigned after sort
            )
        )

    scored.sort(key=lambda v: v.final_suspect_score, reverse=True)
    for i, v in enumerate(scored, start=1):
        v.rank = i

    return AISScoreOutput(spill_id=filter_input.spill_id, ranked_vessels=scored)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/detect", response_model=DetectionOutput)
async def detect(
    spill_id: str = Form(...),
    top_left_lat: float = Form(...),
    top_left_lon: float = Form(...),
    pixel_size_deg: float = Form(...),
    image_timestamp: datetime = Form(...),
    source_image: UploadFile = None,
    mask_image: UploadFile = None,
):
    mask_bytes = await mask_image.read()
    return run_detection(
        spill_id=spill_id,
        mask_bytes=mask_bytes,
        top_left_lat=top_left_lat,
        top_left_lon=top_left_lon,
        pixel_size_deg=pixel_size_deg,
        image_timestamp=image_timestamp,
    )


@app.post("/hindcast", response_model=HindcastOutput)
async def hindcast(hindcast_input: HindcastInput):
    return run_hindcast(hindcast_input)


@app.post("/ais/filter-score", response_model=AISScoreOutput)
async def ais_filter_score(filter_input: AISFilterInput):
    return run_ais_filter_and_score(filter_input)


@app.post("/process-spill", response_model=DashboardResponse)
async def process_spill(
    spill_id: str = Form(...),
    top_left_lat: float = Form(...),
    top_left_lon: float = Form(...),
    pixel_size_deg: float = Form(...),
    image_timestamp: datetime = Form(...),
    raw_ais_pings_json: str = Form(...),
    source_image: UploadFile = None,
    mask_image: UploadFile = None,
):
    """
    Single orchestrator endpoint - runs all stages in sequence and returns
    one combined response. Simplest and lowest-risk option for a live demo.
    """
    import json

    mask_bytes = await mask_image.read()
    detection = run_detection(
        spill_id, mask_bytes, top_left_lat, top_left_lon, pixel_size_deg, image_timestamp
    )

    hindcast_input = HindcastInput(
        spill_id=detection.spill_id,
        observed_position=LatLon(lat=detection.centroid_lat, lon=detection.centroid_lon),
        observation_time=detection.detection_timestamp,
    )
    hindcast_output = run_hindcast(hindcast_input)

    raw_pings = [AISPing(**p) for p in json.loads(raw_ais_pings_json)]
    filter_input = AISFilterInput(
        spill_id=detection.spill_id,
        origin_estimate=hindcast_output.origin_estimate,
        backward_path=hindcast_output.backward_path,
        raw_ais_pings=raw_pings,
    )
    ais_output = run_ais_filter_and_score(filter_input)

    return DashboardResponse(
        detection=detection,
        hindcast=hindcast_output,
        ais_scoring=ais_output,
    )


@app.get("/")
async def health():
    return {"status": "ok"}

@app.get("/ais/test-pipeline")
async def test_ais_pipeline():

    result = run_ais_pipeline(
        ais_file_path="data/ais/ais_dataset.csv",
        spill_timestamp="2020-03-06 23:00:00",
        spill_lat=28.88515,
        spill_lon=-89.022008,
        duration_minutes=60,
        radius_km=34,
        top_n=4
    )

    return result.to_dict(orient="records")