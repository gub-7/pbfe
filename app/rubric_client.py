"""HTTP client for the Rubric service (GLB → LEGO LDR)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Callable

import httpx

from .config import config
from .models import BrickSettings

logger = logging.getLogger("brickedup.rubric_client")


async def submit_rubric_job(
    glb_path: str,
    settings: BrickSettings,
) -> str:
    """Upload GLB to Rubric and return job_id.

    Args:
        glb_path: Path to the GLB file.
        settings: Brick conversion settings.

    Returns:
        Rubric job ID string.
    """
    rubric_url = config.RUBRIC_URL

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        with open(glb_path, "rb") as f:
            response = await client.post(
                f"{rubric_url}/jobs",
                files={"file": ("model.glb", f, "model/gltf-binary")},
                data={
                    "studs": str(settings.studs),
                    "catalog": settings.catalog,
                    "rotate_x": str(settings.rotate_x),
                    "rotate_y": str(settings.rotate_y),
                    "rotate_z": str(settings.rotate_z),
                    "max_studs": str(settings.max_studs),
                    "max_plates": str(settings.max_plates),
                },
            )
            response.raise_for_status()
            result = response.json()
            job_id = result["job_id"]
            logger.info("Rubric job created: %s", job_id)
            return job_id


async def poll_rubric_job(
    job_id: str,
    on_progress: Optional[Callable[[str, str], None]] = None,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
) -> dict:
    """Poll Rubric job until completion.

    Args:
        job_id: Rubric job ID.
        on_progress: Callback(status_str, progress_str).
        poll_interval: Seconds between polls.
        timeout: Max seconds to wait.

    Returns:
        Final job status dict.

    Raises:
        RuntimeError: If job fails or times out.
    """
    rubric_url = config.RUBRIC_URL
    elapsed = 0.0

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            resp = await client.get(f"{rubric_url}/jobs/{job_id}")
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", "")
            progress = data.get("progress", "")

            if on_progress:
                on_progress(status, progress)

            if status == "finished":
                return data
            elif status == "failed":
                error = data.get("error", "Unknown error")
                raise RuntimeError(f"Rubric conversion failed: {error}")

    raise RuntimeError(f"Rubric job {job_id} timed out after {timeout}s")


async def download_ldr(job_id: str, output_path: str) -> str:
    """Download the LDR result from a completed Rubric job.

    Returns:
        Path to the downloaded LDR file.
    """
    rubric_url = config.RUBRIC_URL

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp = await client.get(f"{rubric_url}/jobs/{job_id}/result")
        resp.raise_for_status()

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            f.write(resp.content)

        logger.info("Downloaded LDR to %s (%d bytes)", out, len(resp.content))
        return str(out)


async def get_rubric_metadata(job_id: str) -> Optional[dict]:
    """Get metadata/result from a completed Rubric job."""
    rubric_url = config.RUBRIC_URL

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        try:
            resp = await client.get(f"{rubric_url}/jobs/{job_id}")
            resp.raise_for_status()
            data = resp.json()
            return data.get("result")
        except Exception as e:
            logger.warning("Failed to get Rubric metadata: %s", e)
            return None

