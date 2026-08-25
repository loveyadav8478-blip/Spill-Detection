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

    # Create directory

    UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # just validation
    
    if not satellite_image.filename:
        raise ValueError("Satellite image filename is missing")

    if not spill_mask.filename:
        raise ValueError("Spill mask filename is missing")

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

    # file renaming

    image_name = Path(satellite_image.filename)
    mask_name = Path(spill_mask.filename)

    image_filename = (
        f"{image_name.stem}_"
        f"{uuid.uuid4().hex[:6]}"
        f"{image_name.suffix}"
    )

    mask_filename = (
        f"{mask_name.stem}_"
        f"{uuid.uuid4().hex[:6]}"
        f"{mask_name.suffix}"
    )


    image_path = UPLOAD_DIR / image_filename
    mask_path = UPLOAD_DIR / mask_filename

    # save on disk

    try:

        with open(
            image_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                satellite_image.file,
                buffer
            )


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

    # return

    return (
        str(image_path),
        str(mask_path)
    )