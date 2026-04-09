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

# Maximum retries for transient connection failures
MAX_CONNECT_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds


class GPUClusterError(Exception):
    """Raised when the GPU cluster is unreachable or returns an error."""
    pass


async def _check_gpu_reachable() -> bool:
    """Quick connectivity check to the GPU cluster."""
    gpu_url = config.GPU_CLUSTER_URL
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{gpu_url}/api/health")
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        return False


async def check_gpu_health() -> dict:
    """Check GPU cluster health and return status info."""
    gpu_url = config.GPU_CLUSTER_URL
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{gpu_url}/api/health")
            if resp.status_code == 200:
                return {"status": "healthy", "url": gpu_url, "detail": resp.json()}
            return {"status": "unhealthy", "url": gpu_url, "detail": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"status": "unreachable", "url": gpu_url, "detail": f"Cannot connect to GPU cluster at {gpu_url}"}
    except httpx.TimeoutException:
        return {"status": "timeout", "url": gpu_url, "detail": f"GPU cluster at {gpu_url} timed out"}
    except Exception as e:
        return {"status": "error", "url": gpu_url, "detail": str(e)}


async def submit_multiview_job(
    view_paths: dict[str, str],
    category: str = "generic_object",
    pipeline: str = "canonical_mv_hybrid",
    params: Optional[dict] = None,
) -> str:
    """Upload 5 canonical views to GPU cluster and return job_id.

    Args:
        view_paths: Dict mapping view name -> file path (front, back, left, right, top).
        category: Object category hint.
        pipeline: Reconstruction pipeline to use.
        params: Additional pipeline parameters.

    Returns:
        Job ID string.

    Raises:
        GPUClusterError: If the GPU cluster is unreachable or rejects the request.
    """
    gpu_url = config.GPU_CLUSTER_URL
    params = params or {
        "output_resolution": 1024,
        "mesh_resolution": 256,
        "texture_resolution": 2048,
    }

    last_error = None

    for attempt in range(1, MAX_CONNECT_RETRIES + 1):
        try:
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

        except httpx.ConnectError as e:
            last_error = e
            if attempt < MAX_CONNECT_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "GPU cluster connection failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt, MAX_CONNECT_RETRIES, wait, e,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("GPU cluster unreachable after %d attempts: %s", MAX_CONNECT_RETRIES, e)

        except httpx.TimeoutException as e:
            raise GPUClusterError(
                f"GPU cluster at {gpu_url} timed out while uploading views. "
                f"The server may be overloaded or the connection is too slow."
            ) from e

        except httpx.HTTPStatusError as e:
            raise GPUClusterError(
                f"GPU cluster at {gpu_url} rejected the request: HTTP {e.response.status_code}. "
                f"Response: {e.response.text[:500]}"
            ) from e

    # All retries exhausted
    raise GPUClusterError(
        f"Cannot connect to GPU cluster at {gpu_url}. "
        f"Please verify the GPU server is running and GPU_CLUSTER_URL is correct. "
        f"You can check GPU status at GET /api/health"
    )


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
        GPUClusterError: If job fails, times out, or cluster becomes unreachable.
    """
    gpu_url = config.GPU_CLUSTER_URL
    elapsed = 0.0
    consecutive_errors = 0

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            try:
                resp = await client.get(f"{gpu_url}/api/job/{job_id}/status")
                resp.raise_for_status()
                data = resp.json()
                consecutive_errors = 0  # Reset on success

                status = data.get("status", "")
                progress = data.get("progress", 0)

                if on_progress:
                    on_progress(status, progress)

                if status == "completed":
                    return data
                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    raise GPUClusterError(f"GPU reconstruction failed: {error}")

            except httpx.ConnectError:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    raise GPUClusterError(
                        f"Lost connection to GPU cluster at {gpu_url} while polling job {job_id}. "
                        f"The server may have gone down."
                    )
                logger.warning(
                    "GPU cluster poll connection error (attempt %d/5), will retry",
                    consecutive_errors,
                )

            except httpx.TimeoutException:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    raise GPUClusterError(
                        f"GPU cluster at {gpu_url} repeatedly timed out while polling job {job_id}."
                    )

    raise GPUClusterError(f"GPU job {job_id} timed out after {timeout}s")


async def download_glb(job_id: str, output_path: str) -> str:
    """Download the GLB output from a completed GPU cluster job.

    Returns:
        Path to the downloaded GLB file.

    Raises:
        GPUClusterError: If download fails.
    """
    gpu_url = config.GPU_CLUSTER_URL

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            resp = await client.get(f"{gpu_url}/api/job/{job_id}/output")
            resp.raise_for_status()

            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                f.write(resp.content)

            logger.info("Downloaded GLB to %s (%d bytes)", out, len(resp.content))
            return str(out)

    except httpx.ConnectError as e:
        raise GPUClusterError(
            f"Cannot connect to GPU cluster at {gpu_url} to download GLB. "
            f"The server may have gone down."
        ) from e
    except httpx.HTTPStatusError as e:
        raise GPUClusterError(
            f"Failed to download GLB from GPU cluster: HTTP {e.response.status_code}"
        ) from e


async def get_preprocessing_previews(job_id: str) -> dict[str, str]:
    """Fetch preprocessing preview URLs from GPU cluster.

    Returns:
        Dict mapping preview name -> URL.
    """
    gpu_url = config.GPU_CLUSTER_URL

    try:
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

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning("Failed to fetch preprocessing previews: %s", e)
        return {}
