import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage
from rasterio.warp import transform as warp_transform


def analyze_spill(image_path, mask_path):
    with rasterio.open(image_path) as src:
        transform = src.transform
        crs = src.crs
        width = src.width
        height = src.height
        pixel_width = abs(transform.a)
        pixel_height = abs(transform.e)

    with rasterio.open(mask_path) as src:
        mask = src.read(1)

    if mask.shape != (height, width):
        raise ValueError(
            f"Image and mask dimensions do not match: "
            f"{(height, width)} vs {mask.shape}"
        )

    # Mask: 1 = oil spill, 0 = background
    spill = mask > 0

    spill_pixels = int(spill.sum())

    if spill_pixels == 0:
        return {
            "spillDetected": False,
            "spillPixelCount": 0,
            "areaKm2": 0.0
        }

    # -------------------------
    # Area
    # -------------------------
    pixel_area_m2 = pixel_width * pixel_height
    area_km2 = spill_pixels * pixel_area_m2 / 1_000_000

    # -------------------------
    # Spill centroid
    # -------------------------
    rows, cols = np.where(spill)

    xs, ys = rasterio.transform.xy(
        transform,
        rows,
        cols,
        offset="center"
    )

    centroid_x = float(np.mean(xs))
    centroid_y = float(np.mean(ys))

    lon, lat = warp_transform(
        crs,
        "EPSG:4326",
        [centroid_x],
        [centroid_y]
    )

    centroid_lat = float(lat[0])
    centroid_lon = float(lon[0])

    # -------------------------
    # Bounding box
    # -------------------------
    bbox_width_km = (
        (max(xs) - min(xs)) / 1000
    )

    bbox_height_km = (
        (max(ys) - min(ys)) / 1000
    )

    # -------------------------
    # Connected components
    # -------------------------
    labels, component_count = ndimage.label(spill)

    component_sizes = np.bincount(
        labels.ravel()
    )[1:]

    largest_component = (
        int(component_sizes.max())
        if len(component_sizes)
        else 0
    )

    # -------------------------
    # Approximate perimeter
    # -------------------------
    padded = np.pad(
        spill,
        1,
        constant_values=False
    )

    spill_int = spill.astype(np.int32)

    exposed_edges = (
        spill_int * (~padded[1:-1, :-2]).astype(np.int32) +
        spill_int * (~padded[1:-1, 2:]).astype(np.int32) +
        spill_int * (~padded[:-2, 1:-1]).astype(np.int32) +
        spill_int * (~padded[2:, 1:-1]).astype(np.int32)
    )

    perimeter_m = (
        exposed_edges.sum()
        * ((pixel_width + pixel_height) / 2)
    )

    # -------------------------
    # Shape using PCA
    # -------------------------
    points = np.column_stack(
        (np.asarray(xs), np.asarray(ys))
    )

    points -= points.mean(
        axis=0,
        keepdims=True
    )

    if len(points) > 1:
        covariance = np.cov(
            points,
            rowvar=False
        )

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        eigenvalues = np.sort(
            np.maximum(eigenvalues, 0)
        )[::-1]

        major_axis_km = (
            4 * np.sqrt(eigenvalues[0]) / 1000
        )

        minor_axis_km = (
            4 * np.sqrt(eigenvalues[1]) / 1000
        )

        if eigenvalues[0] > 0:
            eccentricity = np.sqrt(
                1 -
                eigenvalues[1] /
                eigenvalues[0]
            )
        else:
            eccentricity = 0

    else:
        major_axis_km = 0
        minor_axis_km = 0
        eccentricity = 0

    return {
        "spillDetected": True,

        # Ground-truth mask currently used.
        # This is NOT ML confidence.
        "detectionConfidence": None,

        "spillPixelCount": spill_pixels,

        "areaKm2": round(
            area_km2,
            4
        ),

        "perimeterKm": round(
            perimeter_m / 1000,
            4
        ),

        "centroid": {
            "latitude": round(
                centroid_lat,
                6
            ),
            "longitude": round(
                centroid_lon,
                6
            )
        },

        "boundingBoxKm": {
            "width": round(
                bbox_width_km,
                4
            ),
            "height": round(
                bbox_height_km,
                4
            )
        },

        "shape": {
            "majorAxisKm": round(
                major_axis_km,
                4
            ),
            "minorAxisKm": round(
                minor_axis_km,
                4
            ),
            "eccentricity": round(
                float(eccentricity),
                6
            )
        },

        "connectedComponents": {
            "count": int(
                component_count
            ),
            "largestComponentPixels": (
                largest_component
            )
        }
    }


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--image",
        required=True
    )

    parser.add_argument(
        "--mask",
        required=True
    )

    parser.add_argument(
        "--output",
        default="spill_result.json"
    )

    args = parser.parse_args()

    result = analyze_spill(
        args.image,
        args.mask
    )

    with open(
        args.output,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=2
        )

    print(
        json.dumps(
            result,
            indent=2
        )
    )