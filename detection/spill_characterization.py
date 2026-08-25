from __future__ import annotations
import logging
from typing import Tuple, cast

import numpy as np
import rasterio

from scipy import ndimage
from rasterio.warp import transform as warp_transform

from detection.SpillDetectionRequest import SpillDetectionRequest
from detection.SpillDetectionResponse import (
    SpillDetectionResponse,
    Centroid,
    BoundingBox,
    SpillShape,
    ConnectedComponents,
)


def detect_spill(
    request: SpillDetectionRequest,
) -> SpillDetectionResponse:
    try:
        """
        Analyze a satellite image and its corresponding
        oil-spill mask.
        Sentinal image - oil spill mask - geometric analysis - response
        """

        # Read image

        with rasterio.open(request.image_path) as src:

            transform = src.transform
            crs = src.crs

            width = src.width
            height = src.height

            pixel_width = abs(transform.a)

            pixel_height = abs(transform.e)

        # Read mask image

        with rasterio.open(request.mask_path) as src:

            mask = src.read(1)

        #Read mask image

        if mask.shape != (height, width):

            raise ValueError(
                "Image and mask dimensions do not match: "
                f"image={(height, width)}, "
                f"mask={mask.shape}"
            )

        # Change it to binary or bool

        # 0  -> background
        # >0 -> oil spill

        spill = mask > 0

        spill_pixels = int(spill.sum())

        # if not spill return
                
        import uuid

        spi  = f"SPILL-{uuid.uuid4().hex.upper()}"
        if spill_pixels == 0:

            return SpillDetectionResponse(
                incident_id= "",
                spill_id=spi,
                spill_detected=False,
                detection_timestamp=(request.image_timestamp),
                confidence_score=None,
                spill_pixel_count=0,
                area_km2=0.0,
                perimeter_km=0.0,
                centroid=Centroid(latitude=0.0, longitude=0.0),
                bounding_box=BoundingBox(width_km=0.0, height_km=0.0),
                shape=SpillShape(
                    major_axis_km=0.0, minor_axis_km=0.0, eccentricity=0.0
                ),
                connected_components=(
                    ConnectedComponents(count=0, largest_component_pixels=0)
                ),
            )

        # area

        pixel_area_m2 = pixel_width * pixel_height

        area_km2 = spill_pixels * pixel_area_m2 / 1_000_000

        # pixel coordinates

        rows, cols = np.where(spill)

        rows, cols = np.where(spill)

        rows_float = rows.astype(np.float64)
        cols_float = cols.astype(np.float64)

        xs = (
            transform.c
            + (cols_float + 0.5) * transform.a
            + (rows_float + 0.5) * transform.b
        )

        ys = (
            transform.f
            + (cols_float + 0.5) * transform.d
            + (rows_float + 0.5) * transform.e
        )

        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)

        xs = np.asarray(xs)
        ys = np.asarray(ys)

        # centroid of overall spill

        centroid_x = float(np.mean(xs))

        centroid_y = float(np.mean(ys))

        # Convert from satellite CRS to WGS84
        transform_result = warp_transform(crs, "EPSG:4326", [centroid_x], [centroid_y])

        lon = list(transform_result[0])
        lat = list(transform_result[1])

        centroid = Centroid(
            latitude=round(float(lat[0]), 6), longitude=round(float(lon[0]), 6)
        )

        # boundary box

        bbox_width_km = (max(xs) - min(xs)) / 1000

        bbox_height_km = (max(ys) - min(ys)) / 1000

        bounding_box = BoundingBox(
            width_km=round(bbox_width_km, 4), height_km=round(bbox_height_km, 4)
        )

        # connected spill components

        label_result = ndimage.label(spill)

        labels, component_count = cast(Tuple[np.ndarray, int], label_result)

        labels = np.asarray(labels, dtype=np.int64)

        component_count = int(component_count)

        component_sizes = np.bincount(labels.ravel())[1:]

        largest_component = int(component_sizes.max()) if len(component_sizes) else 0

        connected_components = ConnectedComponents(
            count=int(component_count), largest_component_pixels=(largest_component)
        )

        # approx perimeter

        padded = np.pad(spill, 1, constant_values=False)

        spill_int = spill.astype(np.int32)

        exposed_edges = (
            spill_int * (~padded[1:-1, :-2]).astype(np.int32)
            + spill_int * (~padded[1:-1, 2:]).astype(np.int32)
            + spill_int * (~padded[:-2, 1:-1]).astype(np.int32)
            + spill_int * (~padded[2:, 1:-1]).astype(np.int32)
        )

        perimeter_m = exposed_edges.sum() * ((pixel_width + pixel_height) / 2)

        perimeter_km = perimeter_m / 1000

        # PCA here

        points = np.column_stack((xs, ys))

        # Center the points
        points -= points.mean(axis=0, keepdims=True)

        if len(points) > 1:

            covariance = np.cov(points, rowvar=False)

            eigenvalues = np.linalg.eigvalsh(covariance)

            # covariance eigenvalues should not
            # theoretically be negative

            eigenvalues = np.maximum(eigenvalues, 0)

            # Largest → smallest
            eigenvalues = np.sort(eigenvalues)[::-1]

            # Approximate dimensions using
            # ±2 standard deviations. also called the min and max in box plots

            major_axis_km = 4 * np.sqrt(eigenvalues[0]) / 1000

            minor_axis_km = 4 * np.sqrt(eigenvalues[1]) / 1000

            if eigenvalues[0] > 0:

                eccentricity = np.sqrt(1 - (eigenvalues[1] / eigenvalues[0]))

            else:

                eccentricity = 0.0

        else:

            major_axis_km = 0.0
            minor_axis_km = 0.0
            eccentricity = 0.0

        shape = SpillShape(
            major_axis_km=round(major_axis_km, 4),
            minor_axis_km=round(minor_axis_km, 4),
            eccentricity=round(float(eccentricity), 6),
        )

        # response

        response = SpillDetectionResponse(
            incident_id="",
            spill_id=spi,
            spill_detected=True,
            detection_timestamp=(request.image_timestamp),
            #no ml conf for now as no model is used yet
            confidence_score=None,
            spill_pixel_count=spill_pixels,
            area_km2=round(area_km2, 4),
            perimeter_km=round(perimeter_km, 4),
            centroid=centroid,
            bounding_box=bounding_box,
            shape=shape,
            connected_components=(connected_components),
        )

        return response

    except Exception as e:
        logging.error("Error in spill char.", e)
        result = SpillDetectionResponse(
            incident_id="",
            spill_id=spi,
            area_km2=0.0,
            bounding_box=BoundingBox(width_km=0.0, height_km=0.0),
            centroid=centroid,
            confidence_score=None,
            connected_components=connected_components,
            detection_timestamp=request.image_timestamp,
            perimeter_km=0.0,
            shape=SpillShape(major_axis_km=0.0, minor_axis_km=0.0, eccentricity=0.0),
            spill_detected=False,
            spill_pixel_count=0,
            status="FAILED",
            message="Failed to run detection",
            error=str(e),
        )
        return result
