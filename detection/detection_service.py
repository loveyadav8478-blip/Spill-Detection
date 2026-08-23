from datetime import datetime

from fastapi import UploadFile

from detection.upload_service import save_uploaded_spill_files
from detection.SpillDetectionRequest import SpillDetectionRequest
from detection.spill_characterization import detect_spill


async def run_spill_detection(
    spill_id: str,
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
    image_path, mask_path = await save_uploaded_spill_files(
        satellite_image=satellite_image,
        spill_mask=spill_mask,
    )

    # Build detection request
    request = SpillDetectionRequest(
        spill_id=spill_id,
        image_path=image_path,
        mask_path=mask_path,
        image_timestamp=image_timestamp,
    )

    # Run detection
    result = detect_spill(request)

    return result