from pathlib import Path
import shutil
import uuid

from fastapi import UploadFile, HTTPException


UPLOAD_DIR = Path("uploads")


async def save_uploaded_spill_files(
    satellite_image: UploadFile,
    spill_mask: UploadFile,
):
    """
    Validate and save uploaded satellite image
    and spill mask.

    Returns:
        tuple[str, str]:
            image_path,
            mask_path
    """

    # ============================================================
    # 1. CREATE UPLOAD DIRECTORY
    # ============================================================

    UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ============================================================
    # 2. VALIDATE SATELLITE IMAGE
    # ============================================================

    if not satellite_image.filename.lower().endswith(
        (".tif", ".tiff")
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Satellite image must be "
                "a .tif or .tiff file"
            )
        )

    # ============================================================
    # 3. VALIDATE SPILL MASK
    # ============================================================

    if not spill_mask.filename.lower().endswith(
        (".tif", ".tiff")
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Spill mask must be "
                "a .tif or .tiff file"
            )
        )

    # ============================================================
    # 4. GENERATE UNIQUE FILENAMES
    # ============================================================

    image_filename = (
        f"{uuid.uuid4()}_"
        f"{satellite_image.filename}"
    )

    mask_filename = (
        f"{uuid.uuid4()}_"
        f"{spill_mask.filename}"
    )

    image_path = (
        UPLOAD_DIR /
        image_filename
    )

    mask_path = (
        UPLOAD_DIR /
        mask_filename
    )

    # ============================================================
    # 5. SAVE SATELLITE IMAGE
    # ============================================================

    try:

        with open(
            image_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                satellite_image.file,
                buffer
            )

        # ========================================================
        # 6. SAVE SPILL MASK
        # ========================================================

        with open(
            mask_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                spill_mask.file,
                buffer
            )

    except Exception as e:

        # Remove partially uploaded files

        if image_path.exists():
            image_path.unlink()

        if mask_path.exists():
            mask_path.unlink()

        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to save uploaded files: {str(e)}"
            )
        )

    finally:

        await satellite_image.close()
        await spill_mask.close()

    # ============================================================
    # 7. RETURN FILE PATHS
    # ============================================================

    return (
        str(image_path),
        str(mask_path)
    )