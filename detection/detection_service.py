from datetime import datetime
from fastapi.responses import HTMLResponse
import logging

from fastapi import UploadFile
from pyparsing import null_debug_action
import uuid

from detection.upload_service import save_uploaded_spill_files
from detection.file_cleanup import delete_file
from detection.SpillDetectionRequest import SpillDetectionRequest
from detection.SpillDetectionResponse import (
    SpillDetectionResponse,
    BoundingBox,
    SpillShape,
    Centroid,
    ConnectedComponents,
)
from detection.spill_characterization import detect_spill


async def run_spill_detection(
    image_timestamp: datetime,
    satellite_image: UploadFile,
    spill_mask: UploadFile,
):
    """
    Complete spill detection workflow.

    1. Save uploaded files
    2. Create SpillDetectionRequest
    3. Run spill characterization
    4. Return detection result
    """

    # Save uploaded files
    try:
        image_path, mask_path = await save_uploaded_spill_files(
            satellite_image=satellite_image,
            spill_mask=spill_mask,
        )

        # Build detection request
        request = SpillDetectionRequest(
            image_path=image_path,
            mask_path=mask_path,
            image_timestamp=image_timestamp,
        )

        # Run detection
        result = detect_spill(request)
        return result
    except Exception as e:
        logging.error("Error in detection service", e)
        return SpillDetectionResponse(
            incident_id="",
            spill_id="",
            detection_timestamp=request.image_timestamp,
            status="FAILED",
            message="Spill detection failed and not be saved on db",
            error=str(e),
            spill_detected=False,
            confidence_score=None,
            spill_pixel_count=0,
            area_km2=0.0,
            perimeter_km=0.0,
            centroid=Centroid(latitude=0.0, longitude=0.0),
            bounding_box=BoundingBox(width_km=0.0, height_km=0.0),
            shape=SpillShape(major_axis_km=0.0, minor_axis_km=0.0, eccentricity=0.0),
            connected_components=ConnectedComponents(
                count=0, largest_component_pixels=0
            ),
        )
    finally:
        delete_file(image_path)
        delete_file(mask_path)
