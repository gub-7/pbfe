"""HTTP client for the GPU Cluster service (5-view → 3D GLB)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Callable

import httpx

from .config import config

logger = logging.getLogger("brickedup.gpu_client")


async def submit_multiview_job(
    view_paths: dict[str, str],
    category: str = "generic_object",
    pipeline: str = "canonical_mv_hybrid",
    params: Optional[dict] = None,
) -> str:
    """Upload 5 canonical views to GPU cluster and return job_id.

    Args:
        view_paths: Dict mapping view name → file path (front, back, left, right, top).
        category: Object category hint.
        pipeline: Reconstruction pipeline to use.
        params: Additional pipeline parameters.

    Returns:
        Job ID string.
    """
    gpu_url = config.GPU_CLUSTER_URL
    params = params or {
        "output_resolution": 1024,
        "mesh_resolution": 256,
        "texture_resolution": 2048,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        files = {}
        file_handles = []
        try:
            for view_name in ["front", "back", "left", "right", "top"]:
                view_path = view_paths.get(view_name)
                if not view_path:
                    raise ValueError(f"Missing {view_name} view")
                fh = open(view_path, "rb")
                file_handles.append(fh)
                files[view_name] = (f"{view_name}.png", fh, "image/png")

            response = await client.post(
                f"{gpu_url}/api/upload_multiview",
                files=files,
                data={
                    "category": category,
                    "pipeline": pipeline,
                    "params": json.dumps(params),
                },
            )
            response.raise_for_status()
            result = response.json()
            job_id = result["job_id"]
            logger.info("GPU cluster job created: %s", job_id)
            return job_id

        finally:
            for fh in file_handles:
                fh.close()


async def poll_gpu_job(
    job_id: str,
    on_progress: Optional[Callable[[str, int], None]] = None,
    poll_interval: float = 3.0,
    timeout: float = 600.0,
) -> dict:
    """Poll GPU cluster job until completion.

    Args:
        job_id: GPU cluster job ID.
        on_progress: Callback(status_str, progress_int).
        poll_interval: Seconds between polls.
        timeout: Max seconds to wait.

    Returns:
        Final job status dict.

    Raises:
        RuntimeError: If job fails or times out.
    """
    gpu_url = config.GPU_CLUSTER_URL
    elapsed = 0.0

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            resp = await client.get(f"{gpu_url}/api/job/{job_id}/status")
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", "")
            progress = data.get("progress", 0)

            if on_progress:
                on_progress(status, progress)

            if status == "completed":
                return data
            elif status == "failed":
                error = data.get("error", "Unknown error")
                raise RuntimeError(f"GPU reconstruction failed: {error}")

    raise RuntimeError(f"GPU job {job_id} timed out after {timeout}s")


async def download_glb(job_id: str, output_path: str) -> str:
    """Download the GLB output from a completed GPU cluster job.

    Returns:
        Path to the downloaded GLB file.
    """
    gpu_url = config.GPU_CLUSTER_URL

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp = await client.get(f"{gpu_url}/api/job/{job_id}/output")
        resp.raise_for_status()

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            f.write(resp.content)

        logger.info("Downloaded GLB to %s (%d bytes)", out, len(resp.content))
        return str(out)


async def get_preprocessing_previews(job_id: str) -> dict[str, str]:
    """Fetch preprocessing preview URLs from GPU cluster.

    Returns:
        Dict mapping preview name → URL.
    """
    gpu_url = config.GPU_CLUSTER_URL

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        resp = await client.get(f"{gpu_url}/api/job/{job_id}/previews")
        resp.raise_for_status()
        data = resp.json()

        previews = {}
        # For multi-view jobs, previews are organized by view
        if "views" in data:
            for view_name, stages in data["views"].items():
                for stage_info in stages:
                    key = f"{stage_info['stage']}_{view_name}"
                    previews[key] = f"{gpu_url}{stage_info['url']}"
        # For single-view jobs
        elif "previews" in data:
            for preview in data["previews"]:
                previews[preview["stage"]] = f"{gpu_url}{preview['url']}"

        return previews

