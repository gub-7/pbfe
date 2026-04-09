"""Pydantic models for the BrickedUp orchestrator API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Pipeline stages
# ──────────────────────────────────────────────────────────────────────

class PipelineStage(str, Enum):
    """Pipeline stage enumeration — drives the frontend stepper."""
    UPLOADED = "uploaded"
    GENERATING_VIEWS = "generating_views"
    PREPROCESSING_3D = "preprocessing_3d"
    RECONSTRUCTING_3D = "reconstructing_3d"
    CONVERTING_TO_BRICK = "converting_to_brick"
    COMPLETE = "complete"
    FAILED = "failed"


# ──────────────────────────────────────────────────────────────────────
# Pipeline status
# ──────────────────────────────────────────────────────────────────────

class PipelineStatus(BaseModel):
    """Full pipeline status response — polled by the frontend."""
    pipeline_id: str
    stage: PipelineStage
    progress: int = Field(0, ge=0, le=100, description="Overall progress 0-100")
    stage_message: str = ""

    # View generation
    generated_views: list[str] = Field(default_factory=list)

    # 3D Preprocessing previews
    preprocessing_previews: dict[str, str] = Field(
        default_factory=dict,
        description="Map of preview name → URL, e.g. {'segmented_front': '/api/...'}"
    )

    # Artifacts ready flags
    glb_ready: bool = False
    glb_textured_ready: bool = False
    ldr_ready: bool = False
    bom_ready: bool = False

    # Metadata from rubric
    rubric_metadata: Optional[dict] = None

    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Brick settings (maps to Rubric CLI options)
# ──────────────────────────────────────────────────────────────────────

class BrickSettings(BaseModel):
    """User-configurable Rubric settings exposed in the frontend UI."""
    studs: int = Field(default=32, ge=8, le=200, description="Target size in studs (longest dimension)")
    catalog: str = Field(default="popup", description="Part catalog name")
    packer: str = Field(default="auto", description="Packing algorithm: auto, 1x1, multipass")
    mode: str = Field(default="sculpture", description="Build mode: sculpture, vehicle, architecture, mechanical, display")
    rotate_x: float = Field(default=0, description="Rotation X degrees")
    rotate_y: float = Field(default=0, description="Rotation Y degrees")
    rotate_z: float = Field(default=0, description="Rotation Z degrees")
    enable_slopes: bool = Field(default=True, description="Enable slope placement")
    enable_hollowing: bool = Field(default=False, description="Enable interior hollowing")
    support_mode: str = Field(default="none", description="Support mode: none, auto, manual")
    build_policy: str = Field(default="balanced", description="Build policy: relaxed, balanced, strict")
    voxelizer: str = Field(default="auto", description="Voxelizer backend: auto, sdf, floodfill")
    max_studs: int = Field(default=200, description="Max studs in any XY dimension")
    max_plates: int = Field(default=600, description="Max plates in Z dimension")
    step_every_z: int = Field(default=3, description="LDraw STEP interval (0=no steps)")
    color_method: str = Field(default="perceptual", description="Color matching: perceptual, simple")


# ──────────────────────────────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────────────────────────────

class PipelineCreateResponse(BaseModel):
    pipeline_id: str
    status: PipelineStage
    message: str


class RebrickRequest(BaseModel):
    settings: BrickSettings


class BOMEntry(BaseModel):
    part_id: str
    part_name: str = ""
    color_name: str = ""
    color_id: int = 0
    quantity: int = 0
    ldraw_id: str = ""


class BOMResponse(BaseModel):
    pipeline_id: str
    entries: list[BOMEntry] = Field(default_factory=list)
    total_parts: int = 0
    unique_parts: int = 0

