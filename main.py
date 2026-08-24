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
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from alchemy import ModuleResult
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

app = FastAPI(title="Oil Spill Detection & Attribution API")

EARTH_RADIUS_KM = 6371.0
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def save_or_update_module_result(
    session: Session, spill_id: str, module_name: str, payload: dict
):
    """
    Inserts a new ModuleResult or updates the existing one if
    (spill_id, module_name) already exists in PostgreSQL.
    """
    record = (
        session.query(ModuleResult)
        .filter(
            ModuleResult.spill_id == spill_id, ModuleResult.module_name == module_name
        )
        .first()
    )

    if record:
        record.result = payload
    else:
        record = ModuleResult(
            spill_id=spill_id, module_name=module_name, result=payload
        )
        session.add(record)


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
        # 1. Create or Update Incident
        # ---------------------------------------------
        incident = Incident(
            spill_id=res.spill_id,
            incident_code=f"INC-{res.spill_id}",
            status=res.status,
        )
        session.merge(incident)

        # ---------------------------------------------
        # 2. Save or Update Detection Result
        # ---------------------------------------------
        save_or_update_module_result(
            session=session,
            spill_id=res.spill_id,
            module_name="detection",
            payload=res.model_dump(mode="json"),
        )

        # ---------------------------------------------
        # 3. Commit
        # ---------------------------------------------
        session.commit()

        # ---------------------------------------------
        # 4. Return detection response
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
        # Save or Update Hindcast Result in PostgreSQL
        # --------------------------------------------------
        save_or_update_module_result(
            session=session,
            spill_id=payload.spill_id,
            module_name="hindcast",
            payload=response.model_dump(mode="json")
        )
        
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

        # Safe upsert
        save_or_update_module_result(
            session=session,
            spill_id=input_data.spill_id,
            module_name="ais",
            payload=combined_result,
        )

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
    coarse_radius_km: float = Form(50.0),
    coarse_time_window_hours: float = Form(6.0),
    trajectory_max_distance_km: float = Form(5.0),
):
    """
    Runs Detection -> Hindcast -> AIS Analysis sequentially in a single call.
    Handles upserts and pipeline data persistence cleanly.
    """
    session = SessionLocal()

    try:
        # ---------------------------------------------------------------------
        # STAGE 1: SPILL DETECTION
        # ---------------------------------------------------------------------
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
        session.merge(incident)  # Works because spill_id is primary key on Incident

        save_or_update_module_result(
            session=session,
            spill_id=detection_res.spill_id,
            module_name="detection",
            payload=detection_res.model_dump(mode="json"),
        )

        # ---------------------------------------------------------------------
        # STAGE 2: HINDCAST RUN
        # ---------------------------------------------------------------------
        hindcast_input = HindcastInput(
            spill_id=detection_res.spill_id,
            observed_position=LatLon(
                lat=detection_res.centroid.latitude,
                lon=detection_res.centroid.longitude,
            ),
            observation_time=detection_res.detection_timestamp,
        )

        hindcast_res = run_hindcast(hindcast_input)

        save_or_update_module_result(
            session=session,
            spill_id=detection_res.spill_id,
            module_name="hindcast",
            payload=hindcast_res.model_dump(mode="json"),
        )

        # ---------------------------------------------------------------------
        # STAGE 3: AIS FILTER & SCORE
        # ---------------------------------------------------------------------
        ais_input = AISFilterInput(
            spill_id=detection_res.spill_id,
            origin_estimate=hindcast_res.origin_estimate,
            backward_path=hindcast_res.backward_path,
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

        save_or_update_module_result(
            session=session,
            spill_id=detection_res.spill_id,
            module_name="ais",
            payload=ais_combined_payload,
        )

        # ---------------------------------------------------------------------
        # COMMIT TRANSACTION & RETURN
        # ---------------------------------------------------------------------
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
            status_code=500, detail=f"Pipeline execution failed: {str(e)}"
        )

    finally:
        session.close()        


@app.get("/spill-data/prerequisites/{spill_id}")
def get_prerequisite_data(
    spill_id: str,
    target_module: str = Query(..., description="Target module ('hindcast' or 'ais')"),
):
    dependency_map = {"hindcast": "detection", "ais": "hindcast", "detection": "detection"}

    target_module = target_module.lower()
    if target_module not in dependency_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target_module '{target_module}'. Allowed values: {list(dependency_map.keys())}"
        )

    required_module_name = dependency_map[target_module]
    session = SessionLocal()

    try:
        record = session.query(ModuleResult).filter(
            ModuleResult.spill_id == spill_id,
            ModuleResult.module_name == required_module_name,
        ).first()

        if not record:
            # Custom 404 message
            raise HTTPException(
                status_code=404,
                detail=f"Prerequisite step '{required_module_name}' has not been run for spill '{spill_id}'."
            )

        return {
            "spill_id": spill_id,
            "target_module": target_module,
            "fetched_from_module": required_module_name,
            "data": record.result,
        }

    except HTTPException:
        # Re-raise explicit HTTP errors so 404/400 status codes & messages pass through
        raise

    except Exception as e:
        # Custom 500 message for actual database crashes or unexpected errors
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed while fetching prerequisites: {str(e)}"
        )

    finally:
        session.close()


@app.get("/spill-data/result/{spill_id}")
def get_module_result(
    spill_id: str,
    module_name: Optional[str] = Query(
        None,
        description="Optional module filter: 'detection', 'hindcast', or 'ais'. If omitted, returns all module results.",
    ),
):
    """
    Generic fetcher to retrieve stored module payload(s) by spill_id and module_name.
    """
    session = SessionLocal()

    try:
        query = session.query(ModuleResult).filter(ModuleResult.spill_id == spill_id)

        if module_name:
            query = query.filter(ModuleResult.module_name == module_name.lower())

        records = query.all()

        if not records:
            # Custom 404 message
            raise HTTPException(
                status_code=404,
                detail=f"No results found for spill_id '{spill_id}'"
                + (f" with module_name '{module_name}'" if module_name else ""),
            )

        if module_name:
            return {
                "spill_id": spill_id,
                "module_name": records[0].module_name,
                "created_at": records[0].created_at,
                "data": records[0].result,
            }

        return {
            "spill_id": spill_id,
            "modules": {
                rec.module_name: {"created_at": rec.created_at, "data": rec.result}
                for rec in records
            },
        }

    except HTTPException:
        # Re-raise explicit 404s to pass status code & custom message through
        raise

    except Exception as e:
        # Custom 500 message for internal DB query failures
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed while fetching module results: {str(e)}",
        )

    finally:
        session.close()