from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Centroid(BaseModel):
    """
    Geographic center of the detected spill.
    """

    latitude: float = Field(
        ...,
        ge=-90,
        le=90
    )

    longitude: float = Field(
        ...,
        ge=-180,
        le=180
    )


class BoundingBox(BaseModel):
    """
    Approximate rectangular dimensions containing the spill.
    """

    width_km: float
    height_km: float


class SpillShape(BaseModel):
    """
    Shape characteristics calculated using PCA.
    """

    major_axis_km: float

    minor_axis_km: float

    eccentricity: float = Field(
        ...,
        ge=0,
        le=1
    )


class ConnectedComponents(BaseModel):
    """
    Connected regions found in the spill mask.
    """

    count: int

    largest_component_pixels: int


class SpillDetectionResponse(BaseModel):
    """
    Response model
    """
    incident_id: str
    spill_id: str

    spill_detected: bool

    detection_timestamp: datetime

    # None bcz no ml yet.
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0,
        le=1
    )

    spill_pixel_count: int

    area_km2: float

    perimeter_km: float

    centroid: Centroid

    bounding_box: BoundingBox

    shape: SpillShape

    connected_components: ConnectedComponents
    status: str = Field(
    default="SUCCESS",
    description="Processing status of the spill detection request"
    )

    message: str = Field(
        default="Spill detection completed successfully",
        description="Human-readable processing message"
    )

    error: Optional[str] = Field(
        default=None,
        description="Error details when processing fails"
    )