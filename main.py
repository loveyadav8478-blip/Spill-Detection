"""
Basic FastAPI entrypoint wiring the full pipeline:
detection -> hindcast -> AIS filter -> AIS score -> dashboard

Each stage is implemented as a plain function (not a network call) so the
whole pipeline runs in-process for the prototype - matches the "modular
monolith, not distributed microservices" plan.

Run with:  uvicorn main:app --reload
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timedelta

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, Form, File
from PIL import Image
from shapely.geometry import Point, LineString
from detection.detection_service import run_spill_detection
from detection.SpillDetectionResponse import SpillDetectionResponse

from fastapi import FastAPI, HTTPException

from data.schemas import (
    AISFilterInput,
    AISFilterOutput,
    AISScoreOutput
)

from ais_analysis.pipeline import run_ais_pipeline

from data.schemas import (
    DetectionOutput,
    GeoJSONPolygon,
    HindcastInput,
    HindcastOutput,
    HindcastModelParams,
    EnvironmentVector,
    TimedPoint,
    LatLon,
    AISPing,
    AISFilterInput,
    AISScoreOutput,
    ScoredVessel,
    AnomalyFlags,
    DashboardResponse,
)

app = FastAPI(title="Oil Spill Detection & Attribution API")

EARTH_RADIUS_KM = 6371.0

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/detect", response_model=DetectionOutput)
async def detect(
    spill_id: str = Form(...),
    top_left_lat: float = Form(...),
    top_left_lon: float = Form(...),
    pixel_size_deg: float = Form(...),
    image_timestamp: datetime = Form(...),
    source_image: UploadFile = None,
    mask_image: UploadFile = None,
):
    mask_bytes = await mask_image.read()
    return run_detection(
        spill_id=spill_id,
        mask_bytes=mask_bytes,
        top_left_lat=top_left_lat,
        top_left_lon=top_left_lon,
        pixel_size_deg=pixel_size_deg,
        image_timestamp=image_timestamp,
    )


@app.post("/hindcast", response_model=HindcastOutput)
async def hindcast(hindcast_input: HindcastInput):
    return run_hindcast(hindcast_input)


@app.post("/ais/filter-score", response_model=AISScoreOutput)
async def ais_filter_score(filter_input: AISFilterInput):
    return run_ais_filter_and_score(filter_input)


@app.post("/process-spill", response_model=DashboardResponse)
async def process_spill(
    spill_id: str = Form(...),
    top_left_lat: float = Form(...),
    top_left_lon: float = Form(...),
    pixel_size_deg: float = Form(...),
    image_timestamp: datetime = Form(...),
    raw_ais_pings_json: str = Form(...),
    source_image: UploadFile = None,
    mask_image: UploadFile = None,
):
    """
    Single orchestrator endpoint - runs all stages in sequence and returns
    one combined response. Simplest and lowest-risk option for a live demo.
    """
    import json

    mask_bytes = await mask_image.read()
    detection = run_detection(
        spill_id, mask_bytes, top_left_lat, top_left_lon, pixel_size_deg, image_timestamp
    )

    hindcast_input = HindcastInput(
        spill_id=detection.spill_id,
        observed_position=LatLon(lat=detection.centroid_lat, lon=detection.centroid_lon),
        observation_time=detection.detection_timestamp,
    )
    hindcast_output = run_hindcast(hindcast_input)

    raw_pings = [AISPing(**p) for p in json.loads(raw_ais_pings_json)]
    filter_input = AISFilterInput(
        spill_id=detection.spill_id,
        origin_estimate=hindcast_output.origin_estimate,
        backward_path=hindcast_output.backward_path,
        raw_ais_pings=raw_pings,
    )
    ais_output = run_ais_filter_and_score(filter_input)

    return DashboardResponse(
        detection=detection,
        hindcast=hindcast_output,
        ais_scoring=ais_output,
    )


@app.get("/")
async def health():
    return {"status": "ok"}



@app.post("/spill-detection/upload", response_model=SpillDetectionResponse)
async def upload_spill_detection(
    spill_id: str = Form(...),
    image_timestamp: datetime = Form(...),
    satellite_image: UploadFile = File(...),
    spill_mask: UploadFile = File(...),
):
    return await run_spill_detection(
        spill_id=spill_id,
        image_timestamp=image_timestamp,
        satellite_image=satellite_image,
        spill_mask=spill_mask,
    )


@app.get("/ais/test-pipeline")
async def test_ais_pipeline():

    result = run_ais_pipeline(
        ais_file_path="data/ais/ais_dataset.csv",
        spill_timestamp="2020-03-06 23:00:00",
        spill_lat=28.88515,
        spill_lon=-89.022008,
        duration_minutes=60,
        radius_km=34,
        top_n=4
    )

    return result.to_dict(orient="records")


@app.post("/ais/analyze")
def analyze_ais(
    input_data: AISFilterInput
):
    try:

        filter_output, score_output = (
            run_ais_pipeline(
                input_data=input_data
            )
        )

        return {
            "filter_output": filter_output,
            "score_output": score_output
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )