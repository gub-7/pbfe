"""BrickedUp Backend API — orchestrates image generation, 3D reconstruction, and LEGO conversion."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import config
from .models import (
    BrickSettings,
    PipelineCreateResponse,
    PipelineStage,
    PipelineStatus,
    RebrickRequest,
)
from .pipeline import PipelineManager
from . import gpu_client

# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("brickedup")

# ──────────────────────────────────────────────────────────────────────
# Create directories
# ──────────────────────────────────────────────────────────────────────
config.ensure_dirs()

# ──────────────────────────────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="BrickedUp API",
    description="Image → Multi-View → 3D Model → LEGO Brick Model",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline_mgr = PipelineManager()


# ──────────────────────────────────────────────────────────────────────
# Health & Info
# ──────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "BrickedUp API",
        "version": "1.0.0",
        "description": "Image → LEGO pipeline orchestrator",
    }


@app.get("/health")
async def health():
    gpu_health = await gpu_client.check_gpu_health()
    return {
        "status": "healthy",
        "gpu_cluster": gpu_health,
    }


# ──────────────────────────────────────────────────────────────────────
# Pipeline lifecycle
# ──────────────────────────────────────────────────────────────────────

@app.post("/api/pipeline/start", response_model=PipelineCreateResponse)
async def start_pipeline(
    file: UploadFile = File(..., description="Image of subject (corner angle showing ~3 sides)"),
    debug_alignment: bool = False,
):
    """Upload an image and start the full pipeline."""
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    ext = Path(file.filename or "image.png").suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Invalid file type. Allowed: {', '.join(allowed)}")

    state = pipeline_mgr.create_pipeline()

    upload_dir = Path(config.UPLOAD_DIR) / state.pipeline_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"input{ext}"

    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    state.input_image_path = str(upload_path)
    state.debug_alignment = debug_alignment
    logger.info("Pipeline %s: saved upload to %s", state.pipeline_id, upload_path)

    pipeline_mgr.start_pipeline(state.pipeline_id)

    return PipelineCreateResponse(
        pipeline_id=state.pipeline_id,
        status=PipelineStage.UPLOADED,
        message="Pipeline started. Poll /api/pipeline/{id}/status for updates.",
    )


@app.get("/api/pipeline/{pipeline_id}/status", response_model=PipelineStatus)
async def get_pipeline_status(pipeline_id: str):
    """Get the current status of a pipeline."""
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, f"Pipeline {pipeline_id} not found")
    return state.to_status()


@app.post("/api/pipeline/{pipeline_id}/rebrick")
async def rebrick_pipeline(pipeline_id: str, request: RebrickRequest):
    """Re-run LEGO conversion with new brick settings."""
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, f"Pipeline {pipeline_id} not found")
    if not state.glb_path:
        raise HTTPException(400, "3D model not ready yet.")

    try:
        await pipeline_mgr.rebrick(pipeline_id, request.settings)
        return {"status": "started", "message": "Re-conversion started with new settings"}
    except Exception as e:
        raise HTTPException(500, str(e))


# ──────────────────────────────────────────────────────────────────────
# Camera calibration (sends view images directly to GPU cluster)
# ──────────────────────────────────────────────────────────────────────


def _get_view_image_paths(state) -> dict[str, str]:
    """Extract view image paths from pipeline state.

    Works whether the pipeline has a gpu_job_id or not — we only need
    the locally-generated view images.

    Returns:
        Dict mapping view name → local file path.

    Raises:
        HTTPException 400 if views are not yet available.
    """
    if not state.generated_views:
        raise HTTPException(400, "Views have not been generated yet")

    paths: dict[str, str] = {}
    for view_name in ["front", "side", "top"]:
        path = state.generated_views.get(view_name)
        if not path or not Path(path).exists():
            raise HTTPException(
                400,
                f"View '{view_name}' not available. "
                f"Wait for view generation to complete.",
            )
        paths[view_name] = path

    return paths


class CameraCalibrationRequest(BaseModel):
    cameras: dict = {}
    grid_resolution: int = 64
    grid_half_extent: float = 1.0
    sensor_width_mm: float = 36.0
    consensus_ratio: float = 0.6
    mask_dilation: int = 15


@app.post("/api/pipeline/{pipeline_id}/calibrate_cameras")
async def calibrate_cameras(pipeline_id: str, request: CameraCalibrationRequest):
    """Run fast camera calibration preview with overridden camera params.

    Sends the generated view images directly to the GPU cluster.
    Does NOT require the GPU pipeline to have run.

    The ``cameras`` dict supports per-view keys:
        yaw_deg, pitch_deg, distance, focal_length,
        up_hint ([x,y,z]), rotation_deg (0/90/180/270),
        flip_h (bool), flip_v (bool).
    """
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, "Pipeline not found")

    image_paths = _get_view_image_paths(state)

    try:
        result = await gpu_client.calibrate_cameras(
            image_paths,
            {
                "cameras": request.cameras,
                "grid_resolution": request.grid_resolution,
                "grid_half_extent": request.grid_half_extent,
                "sensor_width_mm": request.sensor_width_mm,
                "consensus_ratio": request.consensus_ratio,
                "mask_dilation": request.mask_dilation,
            },
        )
        return result
    except gpu_client.GPUClusterError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        logger.error("Calibration failed for pipeline %s: %s", pipeline_id, e)
        raise HTTPException(500, str(e))


@app.post("/api/pipeline/{pipeline_id}/calibrate_sweep")
async def calibrate_sweep(pipeline_id: str):
    """Brute-force sweep all camera orientation combos per view.

    Sends the generated view images directly to the GPU cluster.
    Does NOT require the GPU pipeline to have run.
    """
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, "Pipeline not found")

    image_paths = _get_view_image_paths(state)

    try:
        result = await gpu_client.calibrate_sweep(image_paths)
        return result
    except gpu_client.GPUClusterError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        logger.error("Calibration sweep failed for pipeline %s: %s", pipeline_id, e)
        raise HTTPException(500, str(e))


# ──────────────────────────────────────────────────────────────────────
# Artifact downloads
# ──────────────────────────────────────────────────────────────────────

@app.get("/api/pipeline/{pipeline_id}/input-image")
async def get_input_image(pipeline_id: str):
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, "Pipeline not found")
    path = Path(state.input_image_path)
    if not path.exists():
        raise HTTPException(404, "Input image not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/pipeline/{pipeline_id}/view/{view_name}")
async def get_generated_view(pipeline_id: str, view_name: str):
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, "Pipeline not found")
    view_path = state.generated_views.get(view_name)
    if not view_path or not Path(view_path).exists():
        raise HTTPException(404, f"View '{view_name}' not found")
    return FileResponse(view_path, media_type="image/png")


@app.get("/api/pipeline/{pipeline_id}/glb")
async def get_glb_model(pipeline_id: str):
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, "Pipeline not found")
    if not state.glb_path or not Path(state.glb_path).exists():
        raise HTTPException(404, "GLB model not ready yet")
    return FileResponse(
        state.glb_path,
        media_type="model/gltf-binary",
        filename="model.glb",
    )


@app.get("/api/pipeline/{pipeline_id}/ldr")
async def get_ldr_model(pipeline_id: str):
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, "Pipeline not found")
    if not state.ldr_path or not Path(state.ldr_path).exists():
        raise HTTPException(404, "LDR model not ready yet")
    return FileResponse(
        state.ldr_path,
        media_type="application/x-ldraw",
        filename="model.ldr",
    )


@app.get("/api/pipeline/{pipeline_id}/bom")
async def get_bom(pipeline_id: str):
    state = pipeline_mgr.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(404, "Pipeline not found")
    if not state.metadata_path or not Path(state.metadata_path).exists():
        raise HTTPException(404, "BOM not available yet")
    return FileResponse(
        state.metadata_path,
        media_type="application/json",
        filename="bom.json",
    )


# ──────────────────────────────────────────────────────────────────────
# Serve static frontend in production
# ──────────────────────────────────────────────────────────────────────
_client_dist = Path(__file__).parent.parent / "static"
if _client_dist.exists():
    app.mount("/", StaticFiles(directory=str(_client_dist), html=True), name="static")

