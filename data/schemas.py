"""
Pydantic schemas for the full oil spill pipeline:
detection -> hindcast/drift -> AIS filtering -> AIS scoring -> dashboard/report

Note on file uploads: FastAPI endpoints that accept the two detection
images (raw SAR image + mask image, or raw-only if mask is generated
by the model) use `UploadFile` directly in the route signature -
UploadFile is not a Pydantic model and does not belong in this file.
Everything AFTER the image bytes are read and processed is represented
here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, confloat, conint


# ---------------------------------------------------------------------------
# Shared geometry primitives
# ---------------------------------------------------------------------------

class LatLon(BaseModel):
    lat: confloat(ge=-90, le=90)
    lon: confloat(ge=-180, le=180)


class TimedPoint(LatLon):
    """A lat/lon paired with an absolute timestamp - used for path arrays."""
    t: datetime


class GeoJSONPolygon(BaseModel):
    """Minimal GeoJSON polygon representation for the spill mask."""
    type: str = Field(default="Polygon", frozen=True)
    coordinates: list[list[list[float]]]  # [ [ [lon, lat], [lon, lat], ... ] ]


# ---------------------------------------------------------------------------
# 1. Detection module
# ---------------------------------------------------------------------------

class DetectionRequest(BaseModel):
    """
    Metadata accompanying the two-image upload (raw SAR image + mask image).
    The actual image bytes travel as multipart UploadFile fields in the
    FastAPI route, not in this model - this covers everything else the
    endpoint needs alongside them.
    """
    spill_id: str
    source_image_filename: str
    mask_image_filename: str
    image_timestamp: datetime
    # geotransform needed to convert pixel-space mask -> real lat/lon polygon
    top_left_lat: float
    top_left_lon: float
    pixel_size_deg: float


class DetectionOutput(BaseModel):
    spill_id: str
    detected_mask: GeoJSONPolygon
    area_km2: float
    perimeter_km: float
    centroid_lat: confloat(ge=-90, le=90)
    centroid_lon: confloat(ge=-180, le=180)
    detection_timestamp: datetime
    confidence_score: confloat(ge=0, le=1)


# ---------------------------------------------------------------------------
# 2. Hindcast / drift module
# ---------------------------------------------------------------------------

class HindcastInput(BaseModel):
    """Subset of DetectionOutput actually needed by hindcast - detection
    stays free of any environmental/weather knowledge."""
    spill_id: str
    observed_position: LatLon
    observation_time: datetime


class EnvironmentVector(BaseModel):
    """Fetched internally by the hindcast module - never supplied by
    detection or by the caller."""
    speed_kmh: float
    direction_deg: confloat(ge=0, lt=360)
    source: str = Field(description="'static_sample' or 'live_api'")
    data_timestamp: datetime


class HindcastModelParams(BaseModel):
    """Fixed constants, not calculated per-request."""
    windage_coefficient: float = 0.03
    timestep_minutes: conint(gt=0) = 30
    lookback_hours: conint(gt=0) = 12
    lookahead_hours: conint(gt=0) = 12


class HindcastOutput(BaseModel):
    spill_id: str
    origin_estimate: TimedPoint
    backward_path: list[TimedPoint]
    forward_path: list[TimedPoint]
    current_input: EnvironmentVector
    wind_input: EnvironmentVector
    model_params: HindcastModelParams
    is_simplified_model: bool = True
    model_notes: str = (
        "Single representative current/wind vector, deterministic single "
        "path - not a spatially-varying field or ensemble."
    )


# ---------------------------------------------------------------------------
# 3. AIS raw ingestion (matches marinecadastre.gov schema)
# ---------------------------------------------------------------------------

class AISPing(BaseModel):
    mmsi: str
    base_date_time: datetime
    lat: confloat(ge=-90, le=90)
    lon: confloat(ge=-180, le=180)
    sog: float = Field(description="Speed over ground, knots")
    cog: confloat(ge=0, lt=360) = Field(description="Course over ground")
    heading: Optional[confloat(ge=0, lt=360)] = None
    vessel_name: Optional[str] = None
    imo: Optional[str] = None
    call_sign: Optional[str] = None
    vessel_type: Optional[int] = None
    status: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    draft: Optional[float] = None
    cargo: Optional[int] = None
    transceiver_class: Optional[str] = None


# ---------------------------------------------------------------------------
# 4. AIS filtering module
# ---------------------------------------------------------------------------

class AISFilterInput(BaseModel):
    spill_id: str
    origin_estimate: TimedPoint
    backward_path: list[TimedPoint]
    raw_ais_pings: list[AISPing]
    coarse_radius_km: float = 50.0
    coarse_time_window_hours: float = 6.0
    trajectory_max_distance_km: float = 5.0


class FilteredVessel(BaseModel):
    mmsi: str
    trajectory_points: list[TimedPoint]
    passed_coarse_filter: bool
    passed_trajectory_filter: bool


class AISFilterOutput(BaseModel):
    spill_id: str
    candidate_vessels: list[FilteredVessel]


# ---------------------------------------------------------------------------
# 5. AIS scoring module
# ---------------------------------------------------------------------------

class AnomalyFlags(BaseModel):
    ais_gap_detected: bool
    gap_duration_min: float = 0.0
    speed_deviation_score: confloat(ge=0, le=1)
    course_deviation_score: confloat(ge=0, le=1)
    loitering_detected: bool = False


class ScoredVessel(BaseModel):
    mmsi: str
    vessel_name: Optional[str] = None
    trajectory_points: list[TimedPoint]
    min_distance_to_origin_km: float
    time_delta_to_origin_min: float
    anomaly: AnomalyFlags
    final_suspect_score: confloat(ge=0, le=1)
    rank: conint(ge=1)


class AISScoreOutput(BaseModel):
    spill_id: str
    ranked_vessels: list[ScoredVessel]


# ---------------------------------------------------------------------------
# 6. Environmental overlay (optional / tier 3)
# ---------------------------------------------------------------------------

class ZoneType(str, Enum):
    marine_protected_area = "mpa"
    fishery = "fishery"
    coastline = "coastline"


class EnvironmentalOverlayZone(BaseModel):
    zone_name: str
    zone_type: ZoneType
    overlap_pct: confloat(ge=0, le=100)


class EnvironmentalOverlayOutput(BaseModel):
    spill_id: str
    overlapping_zones: list[EnvironmentalOverlayZone]


# ---------------------------------------------------------------------------
# 7. Report / alert generation
# ---------------------------------------------------------------------------

class ReportOutput(BaseModel):
    spill_id: str
    generated_at: datetime
    summary_text: str
    top_suspect_mmsi: Optional[str] = None
    confidence_level: confloat(ge=0, le=1)
    map_snapshot_url: Optional[str] = None


# ---------------------------------------------------------------------------
# 8. Dashboard aggregate - single response the frontend renders from
# ---------------------------------------------------------------------------

class DashboardResponse(BaseModel):
    detection: DetectionOutput
    hindcast: HindcastOutput
    ais_scoring: AISScoreOutput
    environmental_overlay: Optional[EnvironmentalOverlayOutput] = None
    report: Optional[ReportOutput] = None