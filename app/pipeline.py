"""Pipeline manager: orchestrates the full image → views → 3D → LEGO flow."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import config
from .models import BrickSettings, PipelineStage, PipelineStatus

logger = logging.getLogger("brickedup.pipeline")


class PipelineState:
    """In-memory state for a single pipeline run."""

    def __init__(self, pipeline_id: str, input_image_path: str = ""):
        self.pipeline_id = pipeline_id
        self.input_image_path = input_image_path
        self.stage = PipelineStage.UPLOADED
        self.progress = 0
        self.stage_message = "Image uploaded"

        # View generation
        self.generated_views: dict[str, str] = {}

        # 3D reconstruction
        self.gpu_job_id: Optional[str] = None
        self.preprocessing_previews: dict[str, str] = {}
        self.glb_path: Optional[str] = None
        self.glb_textured_path: Optional[str] = None

        # Brick conversion
        self.rubric_job_id: Optional[str] = None
        self.ldr_path: Optional[str] = None
        self.bom_path: Optional[str] = None
        self.metadata_path: Optional[str] = None
        self.rubric_metadata: Optional[dict] = None
        self.brick_settings: BrickSettings = BrickSettings()

        # Error
        self.error: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_status(self) -> PipelineStatus:
        return PipelineStatus(
            pipeline_id=self.pipeline_id,
            stage=self.stage,
            progress=self.progress,
            stage_message=self.stage_message,
            generated_views=list(self.generated_views.keys()),
            preprocessing_previews=self.preprocessing_previews,
            glb_ready=self.glb_path is not None,
            glb_textured_ready=self.glb_textured_path is not None,
            ldr_ready=self.ldr_path is not None,
            bom_ready=self.bom_path is not None or self.metadata_path is not None,
            rubric_metadata=self.rubric_metadata,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.updated_at = datetime.utcnow()


class PipelineManager:
    """Manages all pipeline instances and orchestrates the workflow."""

    def __init__(self):
        self.pipelines: dict[str, PipelineState] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def create_pipeline(self, input_image_path: str = "") -> PipelineState:
        pipeline_id = str(uuid.uuid4())
        state = PipelineState(pipeline_id, input_image_path)
        self.pipelines[pipeline_id] = state
        return state

    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineState]:
        return self.pipelines.get(pipeline_id)

    def start_pipeline(self, pipeline_id: str):
        state = self.pipelines.get(pipeline_id)
        if not state:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        task = asyncio.create_task(self._run_pipeline(state))
        self._tasks[pipeline_id] = task

    async def rebrick(self, pipeline_id: str, settings: BrickSettings):
        state = self.pipelines.get(pipeline_id)
        if not state:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        if not state.glb_path:
            raise ValueError("No GLB model available yet")

        state.update(
            brick_settings=settings,
            stage=PipelineStage.CONVERTING_TO_BRICK,
            progress=70,
            stage_message="Re-converting to LEGO with new settings...",
            ldr_path=None,
            bom_path=None,
            metadata_path=None,
            rubric_job_id=None,
            rubric_metadata=None,
            error=None,
        )

        task = asyncio.create_task(self._run_brick_conversion(state))
        self._tasks[f"{pipeline_id}_rebrick"] = task

    # ──────────────────────────────────────────────────────────────────
    # Full pipeline
    # ──────────────────────────────────────────────────────────────────

    async def _run_pipeline(self, state: PipelineState):
        try:
            # Stage 1: Generate multi-angle views
            await self._generate_views(state)

            # Stage 2: 3D reconstruction (includes preprocessing)
            await self._reconstruct_3d(state)

            # Stage 3: Brick conversion
            await self._run_brick_conversion(state)

            # Done
            state.update(
                stage=PipelineStage.COMPLETE,
                progress=100,
                stage_message="LEGO model ready!",
            )
            logger.info("Pipeline %s complete", state.pipeline_id)

        except Exception as e:
            logger.exception("Pipeline %s failed", state.pipeline_id)
            state.update(
                stage=PipelineStage.FAILED,
                error=str(e),
                stage_message=f"Failed: {e}",
            )

    # ──────────────────────────────────────────────────────────────────
    # Stage 1: View generation
    # ──────────────────────────────────────────────────────────────────

    async def _generate_views(self, state: PipelineState):
        state.update(
            stage=PipelineStage.GENERATING_VIEWS,
            progress=5,
            stage_message="Generating multi-angle views with AI...",
        )

        views_dir = str(Path(config.VIEWS_DIR) / state.pipeline_id)

        try:
            if config.OPENAI_API_KEY:
                from .view_generator import generate_views

                def on_progress(view_name, status):
                    completed = len(state.generated_views)
                    state.update(
                        progress=5 + (completed * 5),
                        stage_message=f"Generating {view_name} view ({status})...",
                    )

                views = await generate_views(
                    input_image_path=state.input_image_path,
                    output_dir=views_dir,
                    on_progress=on_progress,
                )
            else:
                logger.warning("No OPENAI_API_KEY set; using fallback")
                from .view_generator import generate_views_fallback
                views = await generate_views_fallback(
                    input_image_path=state.input_image_path,
                    output_dir=views_dir,
                )
        except Exception as e:
            logger.warning("AI view generation failed (%s), using fallback", e)
            from .view_generator import generate_views_fallback
            views = await generate_views_fallback(
                input_image_path=state.input_image_path,
                output_dir=views_dir,
            )

        state.update(
            generated_views=views,
            progress=30,
            stage_message=f"Generated {len(views)} views",
        )
        logger.info("Generated %d views for pipeline %s", len(views), state.pipeline_id)

    # ──────────────────────────────────────────────────────────────────
    # Stage 2: 3D reconstruction
    # ──────────────────────────────────────────────────────────────────

    async def _reconstruct_3d(self, state: PipelineState):
        from . import gpu_client
        from .gpu_client import GPUClusterError

        # Pre-flight: check GPU cluster connectivity
        state.update(
            stage=PipelineStage.PREPROCESSING_3D,
            progress=32,
            stage_message="Checking GPU cluster connectivity...",
        )

        gpu_health = await gpu_client.check_gpu_health()
        if gpu_health["status"] != "healthy":
            raise GPUClusterError(
                f"GPU cluster is {gpu_health['status']} at {gpu_health['url']}. "
                f"{gpu_health.get('detail', '')} "
                f"Please ensure the GPU server is running and GPU_CLUSTER_URL is set correctly in your .env file."
            )

        state.update(
            stage_message="Uploading views for 3D preprocessing...",
        )

        # Submit to GPU cluster
        job_id = await gpu_client.submit_multiview_job(state.generated_views)
        state.update(gpu_job_id=job_id)

        # Switch to reconstruction stage
        state.update(
            stage=PipelineStage.RECONSTRUCTING_3D,
            progress=35,
            stage_message="3D reconstruction in progress...",
        )

        # Poll for completion, updating previews along the way
        def on_progress(status: str, progress: int):
            mapped = 35 + int(progress * 0.30)
            state.update(
                progress=mapped,
                stage_message=f"3D reconstruction: {status} ({progress}%)",
            )

        await gpu_client.poll_gpu_job(job_id, on_progress=on_progress)

        # Fetch preprocessing previews (segmentation masks, etc.)
        try:
            previews = await gpu_client.get_preprocessing_previews(job_id)
            state.update(preprocessing_previews=previews)
        except Exception as e:
            logger.warning("Failed to fetch preprocessing previews: %s", e)

        # Download GLB
        state.update(progress=65, stage_message="Downloading 3D model...")
        glb_dir = Path(config.MODELS_DIR) / state.pipeline_id
        glb_path = str(glb_dir / "model.glb")
        await gpu_client.download_glb(job_id, glb_path)

        state.update(
            glb_path=glb_path,
            glb_textured_path=glb_path,  # GPU cluster provides textured GLB
            progress=70,
            stage_message="3D model ready, converting to LEGO...",
        )
        logger.info("GLB model saved: %s", glb_path)

    # ──────────────────────────────────────────────────────────────────
    # Stage 3: Brick conversion
    # ──────────────────────────────────────────────────────────────────

    async def _run_brick_conversion(self, state: PipelineState):
        from . import rubric_client

        state.update(
            stage=PipelineStage.CONVERTING_TO_BRICK,
            progress=72,
            stage_message="Uploading 3D model to Rubric...",
        )

        # Submit to Rubric
        job_id = await rubric_client.submit_rubric_job(
            state.glb_path, state.brick_settings
        )
        state.update(rubric_job_id=job_id, progress=75)

        # Poll for completion
        def on_progress(status: str, progress_str: str):
            state.update(
                progress=min(state.progress + 1, 94),
                stage_message=f"LEGO conversion: {progress_str or status}",
            )

        result_data = await rubric_client.poll_rubric_job(job_id, on_progress=on_progress)

        # Download LDR
        state.update(progress=95, stage_message="Downloading LEGO model...")
        output_dir = Path(config.OUTPUT_DIR) / state.pipeline_id
        ldr_path = str(output_dir / "model.ldr")
        await rubric_client.download_ldr(job_id, ldr_path)
        state.update(ldr_path=ldr_path)

        # Save metadata
        try:
            rubric_result = result_data.get("result", {})
            if rubric_result:
                metadata_path = str(output_dir / "metadata.json")
                with open(metadata_path, "w") as f:
                    json.dump(rubric_result, f, indent=2)
                state.update(
                    metadata_path=metadata_path,
                    bom_path=metadata_path,
                    rubric_metadata=rubric_result,
                )
        except Exception as e:
            logger.warning("Failed to save metadata: %s", e)

        state.update(progress=98, stage_message="LEGO model ready!")
        logger.info("LEGO model saved: %s", ldr_path)

