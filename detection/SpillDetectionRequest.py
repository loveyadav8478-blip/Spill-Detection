from datetime import datetime
from pydantic import BaseModel, Field


class SpillDetectionRequest(BaseModel):
    """
    Request contract for oil-spill detection/characterization.

    Required:
    1. Sentinel-1 satellite image
    2. Corresponding oil-spill mask
    """

    spill_id: str = Field(
        "20200307",
        description="Unique identifier for the spill incident"
    )

    image_path: str = Field(
        "data/satelite/20200307.tif",
        description="Path to the Sentinel-1 satellite image"
    )

    mask_path: str = Field(
        "data/satelite/20200307_mask.tif",
        description="Path to the corresponding oil-spill mask"
    )

    image_timestamp: datetime = Field(
        datetime(2020, 3, 7, 0, 0) ,
        description="Timestamp of the satellite observation"
    )