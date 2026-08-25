from datetime import datetime
from pydantic import BaseModel, Field


class SpillDetectionRequest(BaseModel):
    """
    Request Schema for detection
    """

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