"""Client for communicating with the GPU cluster 3D reconstruction service.

Handles multi-view job submission, polling, preview fetching, and
GLB download.  The GPU cluster exposes a FastAPI service (see
gpu-cluster/api/main.py) at the URL configured by GPU_CLUSTER_URL.

3-view canonical setup:
    - front:  perpendicular, centered
    - side:   perpendicular from the right
    - top:    bird's-eye looking straight down
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from .config import config

logger = logging.getLogger("brickedup.gpu_client")

# Canonical view names — must match gpu-cluster/api/models.py ViewName
CANONICAL_VIEWS = ["front", "side", "top"]

# Polling configuration
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 600  # 10 minutes max


class GPUClusterError(Exception):
    """Raised when the GPU cluster returns an error or is unreachable."""


# ──────────────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────────────


async def check_gpu_health() -> dict:
    """Check GPU cluster connectivity and health.

    Returns:
        Dict with keys: status, url, detail.
    """
    url = config.GPU_CLUSTER_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{url}/api/health")
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": data.get("status", "healthy"),
                "url": url,
                "detail": "",
            }
    except Exception as e:
        return {
            "status": "unreachable",
            "url": url,
            "detail": str(e),
        }


# ──────────────────────────────────────────────────────────────────────
# Job submission
# ──────────────────────────────────────────────────────────────────────


async def submit_multiview_job(
    generated_views: dict[str, str],
    category: str = "generic_object",
    pipeline: str = "canonical_mv_hybrid",
    params: Optional[dict] = None,
) -> str:
    """Submit a multi-view reconstruction job to the GPU cluster.

    Args:
        generated_views: Dict mapping view name → local file path.
            Expected keys: front, side, top.
        category: Object category for reconstruction hints.
        pipeline: GPU cluster pipeline to use.
        params: Optional CanonicalMVParams overrides.

    Returns:
        Job ID from the GPU cluster.

    Raises:
        GPUClusterError: If submission fails.
    """
    url = config.GPU_CLUSTER_URL.rstrip("/")

    files = {}
    for view_name in CANONICAL_VIEWS:
        path = generated_views.get(view_name)
        if not path:
            raise GPUClusterError(
                f"Missing required view '{view_name}' in generated_views"
            )
        filepath = Path(path)
        if not filepath.exists():
            raise GPUClusterError(
                f"View file not found: {path}"
            )
        files[view_name] = (
            filepath.name,
            open(filepath, "rb"),
            "image/png",
        )

    data = {
        "category": category,
        "pipeline": pipeline,
    }
    if params:
        import json
        data["params"] = json.dumps(params)
    else:
        data["params"] = "{}"

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{url}/api/upload_multiview",
                files=files,
                data=data,
            )
            resp.raise_for_status()
            result = resp.json()
            job_id = result.get("job_id")
            if not job_id:
                raise GPUClusterError(
                    f"GPU cluster did not return a job_id: {result}"
                )
            logger.info("Submitted multi-view job %s to GPU cluster", job_id)
            return job_id
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        raise GPUClusterError(
            f"GPU cluster returned {e.response.status_code}: {detail}"
        ) from e
    except httpx.RequestError as e:
        raise GPUClusterError(
            f"Could not connect to GPU cluster at {url}: {e}"
        ) from e
    finally:
        # Close file handles
        for _name, (_, fh, _mime) in files.items():
            fh.close()


# ──────────────────────────────────────────────────────────────────────
# Polling
# ──────────────────────────────────────────────────────────────────────


async def poll_gpu_job(
    job_id: str,
    on_progress: Optional[callable] = None,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    timeout: float = POLL_TIMEOUT_SECONDS,
) -> dict:
    """Poll a GPU cluster job until completion or failure.

    Args:
        job_id: Job ID to poll.
        on_progress: Optional callback(status_str, progress_int).
        poll_interval: Seconds between polls.
        timeout: Maximum seconds to wait.

    Returns:
        Final job status dict.

    Raises:
        GPUClusterError: If the job fails or times out.
    """
    url = config.GPU_CLUSTER_URL.rstrip("/")
    elapsed = 0.0

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < timeout:
            try:
                resp = await client.get(f"{url}/api/job/{job_id}/status")
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning("Poll error for job %s: %s", job_id, e)
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            status = data.get("status", "unknown")
            progress = data.get("progress", 0)

            if on_progress:
                on_progress(status, progress)

            if status == "completed":
                logger.info("GPU job %s completed", job_id)
                return data

            if status == "failed":
                error = data.get("error", "Unknown error")
                raise GPUClusterError(
                    f"GPU job {job_id} failed: {error}"
                )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

    raise GPUClusterError(
        f"GPU job {job_id} timed out after {timeout}s"
    )


# ──────────────────────────────────────────────────────────────────────
# Preview fetching
# ──────────────────────────────────────────────────────────────────────


async def get_preprocessing_previews(job_id: str) -> dict[str, str]:
    """Fetch preview image URLs from the GPU cluster.

    Returns:
        Dict mapping preview name → URL path (relative to GPU cluster).
    """
    url = config.GPU_CLUSTER_URL.rstrip("/")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{url}/api/job/{job_id}/previews")
        resp.raise_for_status()
        data = resp.json()

    previews: dict[str, str] = {}

    # Multi-view format: {views: {view_name: [{stage, url}, ...]}}
    views = data.get("views", {})
    for view_name, stages in views.items():
        for stage_info in stages:
            stage = stage_info.get("stage", "")
            preview_url = stage_info.get("url", "")
            if preview_url:
                key = f"{stage}_{view_name}"
                # Return the full URL so the backend can proxy or redirect
                previews[key] = f"{url}{preview_url}"

    return previews


# ──────────────────────────────────────────────────────────────────────
# GLB download
# ──────────────────────────────────────────────────────────────────────


async def download_glb(job_id: str, output_path: str) -> None:
    """Download the final GLB output from the GPU cluster.

    Args:
        job_id: Completed job ID.
        output_path: Local path to save the GLB file.

    Raises:
        GPUClusterError: If download fails.
    """
    url = config.GPU_CLUSTER_URL.rstrip("/")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(f"{url}/api/job/{job_id}/output")
            resp.raise_for_status()
            with open(out, "wb") as f:
                f.write(resp.content)
        logger.info("Downloaded GLB for job %s → %s", job_id, output_path)
    except httpx.HTTPStatusError as e:
        raise GPUClusterError(
            f"Failed to download GLB: HTTP {e.response.status_code}"
        ) from e
    except httpx.RequestError as e:
        raise GPUClusterError(
            f"Failed to download GLB from {url}: {e}"
        ) from e

