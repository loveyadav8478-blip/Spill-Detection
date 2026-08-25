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

from sqlalchemy import text
from sqlalchemy.orm import Session
from db import engine
from db import SessionLocal
from alchemy import Incident, ModuleResult, Base

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, Form, File, HTTPException, Query
from PIL import Image
from shapely.geometry import Point, LineString
from detection.detection_service import run_spill_detection
from detection.SpillDetectionResponse import SpillDetectionResponse
from hindcasting.hindcast_service import run_hindcast
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

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Oil Spill Detection & Attribution API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EARTH_RADIUS_KM = 6371.0


@app.on_event("startup")
def test_database_connection():
    try:
        # Automatically creates tables if they don't exist yet
        Base.metadata.create_all(bind=engine)

        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("Database connected:", result.scalar())

    except Exception as e:
        print("Database connection failed:", e)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post("/spill-detection/upload", response_model=SpillDetectionResponse)
async def upload_spill_detection(
    image_timestamp: datetime = Form(...),
    satellite_image: UploadFile = File(...),
    spill_mask: UploadFile = File(...),
):
    # Run existing detection logic
    res = await run_spill_detection(
        image_timestamp=image_timestamp,
        satellite_image=satellite_image,
        spill_mask=spill_mask,
    )

    session = SessionLocal()

    try:

        # ---------------------------------------------
        # 1. Create Incident
        # ---------------------------------------------

        incident = Incident(
            spill_id=res.spill_id,
            incident_code=f"INC-{res.spill_id}",
            status=res.status,
        )

        session.add(incident)

        # ---------------------------------------------
        # 2. Save Detection Result
        # ---------------------------------------------

        module_result = ModuleResult(
            spill_id=res.spill_id,
            module_name="detection",
            result=res.model_dump(mode="json"),
        )

        session.add(module_result)

        # ---------------------------------------------
        # 3. Commit
        # ---------------------------------------------

        session.commit()

        # ---------------------------------------------
        # 4. Return existing detection response
        # ---------------------------------------------

        return res

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


@app.post("/hindcast/rundrifts", response_model=HindcastOutput)
async def run_hindcast_service(payload: HindcastInput):
    response = run_hindcast(payload)

    session = SessionLocal()

    try:

        # --------------------------------------------------
        # Save Hindcast Result
        # --------------------------------------------------

        module_result = ModuleResult(
            spill_id=payload.spill_id,
            module_name="hindcast",
            result=response.model_dump(mode="json"),
        )

        session.add(module_result)

        # --------------------------------------------------
        # Commit
        # --------------------------------------------------

        session.commit()

        return response

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


@app.post("/ais/analyze")
async def analyze_ais(input_data: AISFilterInput):
    try:
        filter_output, score_output = run_ais_pipeline(input_data=input_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    session = SessionLocal()

    try:
        # --------------------------------------------------
        # Save AIS Analysis Result
        # --------------------------------------------------
        combined_result = {
            "filter_output": (
                filter_output.model_dump(mode="json")
                if hasattr(filter_output, "model_dump")
                else filter_output
            ),
            "score_output": (
                score_output.model_dump(mode="json")
                if hasattr(score_output, "model_dump")
                else score_output
            ),
        }

        module_result = ModuleResult(
            spill_id=input_data.spill_id,
            module_name="ais",
            result=combined_result,
        )

        session.add(module_result)

        # --------------------------------------------------
        # Commit
        # --------------------------------------------------
        session.commit()

        return {"filter_output": filter_output, "score_output": score_output}

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


import json

@app.post("/spill-detection/pipeline/full")
async def run_full_spill_pipeline(
    image_timestamp: datetime = Form(...),
    satellite_image: UploadFile = File(...),
    spill_mask: UploadFile = File(...),
    raw_ais_pings_json: str = Form(...),
    coarse_radius_km: float = Form(50.0),
    coarse_time_window_hours: float = Form(6.0),
    trajectory_max_distance_km: float = Form(5.0),
):
    """
    Executes the full pipeline sequentially in one single request:
    1. Detection -> Saves Incident & Detection ModuleResult
    2. Hindcast  -> Saves Hindcast ModuleResult
    3. AIS       -> Saves AIS ModuleResult
    Returns the complete structured dashboard output.
    """
    session = SessionLocal()

    try:
        # =====================================================================
        # STAGE 1: SPILL DETECTION
        # =====================================================================
        detection_res = await run_spill_detection(
            image_timestamp=image_timestamp,
            satellite_image=satellite_image,
            spill_mask=spill_mask,
        )

        incident = Incident(
            spill_id=detection_res.spill_id,
            incident_code=f"INC-{detection_res.spill_id}",
            status=detection_res.status,
        )
        session.add(incident)

        detection_module_result = ModuleResult(
            spill_id=detection_res.spill_id,
            module_name="detection",
            result=detection_res.model_dump(mode="json"),
        )
        session.add(detection_module_result)

        # =====================================================================
        # STAGE 2: HINDCAST RUN
        # =====================================================================
        # Build Hindcast Input from Stage 1 output
        hindcast_input = HindcastInput(
            spill_id=detection_res.spill_id,
            observed_position=LatLon(
                lat=detection_res.centroid.latitude,
                lon=detection_res.centroid.longitude
            ),
            observation_time=detection_res.detection_timestamp,
        )

        hindcast_res = run_hindcast(hindcast_input)

        hindcast_module_result = ModuleResult(
            spill_id=detection_res.spill_id,
            module_name="hindcast",
            result=hindcast_res.model_dump(mode="json"),
        )
        session.add(hindcast_module_result)

        # =====================================================================
        # STAGE 3: AIS FILTER & SCORE
        # =====================================================================
        # Build AIS Input from Stage 2 output and uploaded AIS pings
        parsed_pings = [AISPing(**p) for p in json.loads(raw_ais_pings_json)]
        
        ais_input = AISFilterInput(
            spill_id=detection_res.spill_id,
            origin_estimate=hindcast_res.origin_estimate,
            backward_path=hindcast_res.backward_path,
            raw_ais_pings=parsed_pings,
            coarse_radius_km=coarse_radius_km,
            coarse_time_window_hours=coarse_time_window_hours,
            trajectory_max_distance_km=trajectory_max_distance_km,
        )

        filter_output, score_output = run_ais_pipeline(input_data=ais_input)

        ais_combined_payload = {
            "filter_output": (
                filter_output.model_dump(mode="json")
                if hasattr(filter_output, "model_dump")
                else filter_output
            ),
            "score_output": (
                score_output.model_dump(mode="json")
                if hasattr(score_output, "model_dump")
                else score_output
            ),
        }

        ais_module_result = ModuleResult(
            spill_id=detection_res.spill_id,
            module_name="ais",
            result=ais_combined_payload,
        )
        session.add(ais_module_result)

        # =====================================================================
        # COMMIT TRANSACTION & RETURN
        # =====================================================================
        session.commit()

        return {
            "spill_id": detection_res.spill_id,
            "status": "COMPLETED",
            "detection": detection_res,
            "hindcast": hindcast_res,
            "ais_analysis": {
                "filter_output": filter_output,
                "score_output": score_output,
            },
        }

    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution failed: {str(e)}"
        )

    finally:
        session.close()

@app.get("/spill-data/prerequisites/{spill_id}")
def get_prerequisite_data(
    spill_id: str,
    target_module: str = Query(
        ..., description="The module you want to run next (e.g., 'hindcast' or 'ais')"
    ),
):
    """
    Fetches the necessary prior module data needed to run the target_module.
    - If target_module == 'hindcast', it fetches 'detection' results.
    - If target_module == 'ais', it fetches 'hindcast' results.
    """

    # Map what data is required for each target module
    dependency_map = {"hindcast": "detection", "ais": "hindcast"}

    if target_module not in dependency_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target_module. Must be one of {list(dependency_map.keys())}",
        )

    required_module_name = dependency_map[target_module]
    session = SessionLocal()

    try:
        # Fetch the required prerequisite data from the database
        record = (
            session.query(ModuleResult)
            .filter(
                ModuleResult.spill_id == spill_id,
                ModuleResult.module_name == required_module_name,
            )
            .first()
        )

        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Required prerequisite data from '{required_module_name}' not found for spill_id '{spill_id}'.",
            )

        return {
            "spill_id": spill_id,
            "target_module": target_module,
            "fetched_from_module": required_module_name,
            "data": record.result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        session.close()
