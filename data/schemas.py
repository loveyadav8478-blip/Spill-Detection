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
from typing import Annotated, Optional

from pydantic import BaseModel, Field

Lat = Annotated[float, Field(ge=-90, le=90)]
Lon = Annotated[float, Field(ge=-180, le=180)]
Deg360 = Annotated[float, Field(ge=0, lt=360)]
Unit = Annotated[float, Field(ge=0, le=1)]
Pct100 = Annotated[float, Field(ge=0, le=100)]
PositiveInt = Annotated[int, Field(gt=0)]
RankInt = Annotated[int, Field(ge=1)]


class TimeSource(str, Enum):
    """Where detection_timestamp actually came from - makes the
    disclosed-assumption pattern a real, inspectable field instead of
    an undocumented guess. 'assumed_ltan' = no real timestamp was
    recoverable from the file, so a representative time was assumed
    based on Sentinel-1's known dawn-dusk local overpass time."""
    filename = "filename"
    manifest = "manifest"
    exif = "exif"
    csv_metadata = "csv_metadata"
    assumed_ltan = "assumed_ltan"
    unknown = "unknown"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    HINDCASTING = "HINDCASTING"
    FILTERING = "FILTERING"
    SCORING = "SCORING"
    ATTRIBUTED = "ATTRIBUTED"


# ---------------------------------------------------------------------------
# Shared geometry primitives
# ---------------------------------------------------------------------------

class LatLon(BaseModel):
    lat: Lat
    lon: Lon


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
    centroid_lat: Lat
    centroid_lon: Lon
    detection_timestamp: datetime
    confidence_score: Unit
    sar_file_path: Optional[str] = None
    observation_time: Optional[datetime] = None  # None when time-of-day is genuinely unknown
    time_source: TimeSource = TimeSource.unknown


# ---------------------------------------------------------------------------
# 2. Hindcast / drift module
# ---------------------------------------------------------------------------

class HindcastInput(BaseModel):
    """Subset of DetectionOutput actually needed by hindcast - detection
    stays free of any environmental/weather knowledge."""
    spill_id: str
    observed_position: LatLon
    observation_time: datetime


class EnvironmentSource(str, Enum):
    static_sample = "static_sample"
    synthetic_dataset = "synthetic_dataset"
    live_api = "live_api"


class EnvironmentVector(BaseModel):
    """Fetched internally by the hindcast module - never supplied by
    detection or by the caller."""
    speed_kmh: float
    direction_deg: Deg360
    source: EnvironmentSource
    data_timestamp: datetime


class HindcastModelParams(BaseModel):
    """Fixed constants, not calculated per-request."""
    windage_coefficient: float = 0.03
    timestep_minutes: PositiveInt = 30
    lookback_hours: PositiveInt = 12
    lookahead_hours: PositiveInt = 12


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
    lat: Lat
    lon: Lon
    sog: float = Field(description="Speed over ground, knots")
    cog: Deg360 = Field(description="Course over ground")
    heading: Optional[Deg360] = None
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
    speed_deviation_score: Unit
    course_deviation_score: Unit
    loitering_detected: bool = False


class ScoringWeights(BaseModel):
    """The weights actually used to combine component scores into
    final_suspect_score - surfaced so the value is inspectable, not
    just baked silently into the arithmetic."""
    proximity: float = 0.4
    temporal: float = 0.15
    trajectory: float = 0.15
    behavior: float = 0.3


class ScoredVessel(BaseModel):
    mmsi: str
    vessel_name: Optional[str] = None
    # vessel metadata - was already present in AISPing but dropped
    # before reaching this model; now carried through.
    imo: Optional[str] = None
    call_sign: Optional[str] = None
    vessel_type: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None

    trajectory_points: list[TimedPoint]
    min_distance_to_origin_km: float
    time_delta_to_origin_min: float
    anomaly: AnomalyFlags

    # component scores - were computed internally already, now exposed
    proximity_score: Unit
    temporal_score: Unit
    trajectory_score: Unit
    behavior_score: Unit

    final_suspect_score: Unit
    rank: RankInt

    explanation: list[str] = Field(default_factory=list)
    weights_used: ScoringWeights = Field(default_factory=ScoringWeights)


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
    overlap_pct: Pct100


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
    confidence_level: Unit
    map_snapshot_url: Optional[str] = None


# ---------------------------------------------------------------------------
# 8. Incident record - lifecycle wrapper. Doesn't belong to detection,
# hindcast, or AIS individually (each of those stays a pure function of
# its own inputs) - this is assembled by the orchestrator from pieces
# of DetectionOutput + HindcastOutput plus pipeline-run metadata.
# ---------------------------------------------------------------------------

class IncidentRecord(BaseModel):
    id: int
    incident_code: str
    observation_date: str  # date-only, e.g. "2020-03-07" - always available
    observation_time: Optional[datetime] = None  # None if genuinely unrecoverable
    time_source: TimeSource
    sar_file_path: Optional[str] = None
    is_simplified_model: bool
    model_notes: str
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 9. Attribution response - the exact per-vessel record the frontend
# consumes. Built by the API layer from IncidentRecord + ScoredVessel;
# neither of those two models is reduced to produce this, this just
# reshapes/rescales them into the frontend's expected contract
# (0-100 scores, JSON-encoded string fields for explanation/weights
# to match how the frontend currently stores/parses them).
# ---------------------------------------------------------------------------

class VesselSummary(BaseModel):
    mmsi: str
    vessel_name: Optional[str] = None
    imo: Optional[str] = None
    call_sign: Optional[str] = None
    vessel_type: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None


class AttributionResponse(BaseModel):
    id: int
    incident: IncidentRecord
    vessel: VesselSummary
    proximity_score: Pct100
    temporal_score: Pct100
    trajectory_score: Pct100
    behavior_score: Pct100
    attribution_score: Pct100
    explanation_json: str  # JSON-encoded list[str] - matches frontend's current storage shape
    weights_used_json: str  # JSON-encoded dict - same reason




class DashboardResponse(BaseModel):
    detection: DetectionOutput
    hindcast: HindcastOutput
    ais_scoring: AISScoreOutput
    environmental_overlay: Optional[EnvironmentalOverlayOutput] = None
    report: Optional[ReportOutput] = None