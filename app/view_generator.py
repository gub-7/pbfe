"""Multi-view image generation using OpenAI's image generation API.

Given a single corner-angle photo, generates the 5 canonical views
(front, back, left, right, top) needed for 3D reconstruction.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Optional

from .config import config

logger = logging.getLogger("brickedup.views")

CANONICAL_VIEWS = ["front", "back", "left", "right", "top"]

VIEW_PROMPTS = {
    "front": (
        "Generate a clean front view of this exact same object/subject. "
        "The camera is directly in front, looking straight at the subject. "
        "Same lighting, same object, same colors, same details. "
        "Pure white background. No shadows. Centered in frame."
    ),
    "back": (
        "Generate a clean back view of this exact same object/subject. "
        "The camera is directly behind, looking at the back. "
        "Same lighting, same object, same colors, same details. "
        "Pure white background. No shadows. Centered in frame."
    ),
    "left": (
        "Generate a clean left-side view of this exact same object/subject. "
        "The camera is directly to the left, looking at the left side. "
        "Same lighting, same object, same colors, same details. "
        "Pure white background. No shadows. Centered in frame."
    ),
    "right": (
        "Generate a clean right-side view of this exact same object/subject. "
        "The camera is directly to the right, looking at the right side. "
        "Same lighting, same object, same colors, same details. "
        "Pure white background. No shadows. Centered in frame."
    ),
    "top": (
        "Generate a clean top-down view of this exact same object/subject. "
        "The camera is directly above, looking straight down. "
        "Same lighting, same object, same colors, same details. "
        "Pure white background. No shadows. Centered in frame."
    ),
}


async def generate_views(
    input_image_path: str,
    output_dir: str,
    views_to_generate: Optional[list[str]] = None,
    on_progress: Optional[callable] = None,
) -> dict[str, str]:
    """Generate canonical views from a corner-angle input image using OpenAI.

    Args:
        input_image_path: Path to the input image.
        output_dir: Directory to save generated views.
        views_to_generate: Which views to generate (default: all 5).
        on_progress: Callback(view_name, status) for progress updates.

    Returns:
        Dict mapping view name → file path.
    """
    from openai import AsyncOpenAI

    views = views_to_generate or CANONICAL_VIEWS
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read and encode input image
    input_path = Path(input_image_path)
    with open(input_path, "rb") as f:
        image_bytes = f.read()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Determine media type
    mime, _ = mimetypes.guess_type(str(input_path))
    media_type = mime or "image/png"

    client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

    # Save input as the "input" view
    input_copy = out_dir / f"input{input_path.suffix}"
    shutil.copy2(input_path, input_copy)

    results: dict[str, str] = {"input": str(input_copy)}

    # Generate each view concurrently (but with some throttling)
    semaphore = asyncio.Semaphore(2)  # max 2 concurrent API calls

    async def gen_one(view_name: str) -> tuple[str, str]:
        async with semaphore:
            if on_progress:
                on_progress(view_name, "generating")

            output_path = out_dir / f"{view_name}.png"
            prompt = VIEW_PROMPTS[view_name]

            try:
                response = await client.images.edit(
                    model=config.IMAGE_GEN_MODEL,
                    image=open(input_path, "rb"),
                    prompt=prompt,
                    n=1,
                    size="1024x1024",
                )

                # Download the generated image
                image_url = response.data[0].url
                if response.data[0].b64_json:
                    img_data = base64.b64decode(response.data[0].b64_json)
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                elif image_url:
                    import httpx
                    async with httpx.AsyncClient() as http:
                        img_resp = await http.get(image_url)
                        img_resp.raise_for_status()
                        with open(output_path, "wb") as f:
                            f.write(img_resp.content)

                if on_progress:
                    on_progress(view_name, "complete")

                return view_name, str(output_path)

            except Exception as e:
                logger.error("Failed to generate %s view: %s", view_name, e)
                # Fallback: copy input image
                shutil.copy2(input_path, output_path)
                if on_progress:
                    on_progress(view_name, "fallback")
                return view_name, str(output_path)

    tasks = [gen_one(v) for v in views]
    completed = await asyncio.gather(*tasks)

    for view_name, path in completed:
        results[view_name] = path

    return results


async def generate_views_fallback(
    input_image_path: str,
    output_dir: str,
    views_to_generate: Optional[list[str]] = None,
    on_progress: Optional[callable] = None,
) -> dict[str, str]:
    """Fallback: copy input image as all views (for testing without OpenAI key)."""
    views = views_to_generate or CANONICAL_VIEWS
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(input_image_path)
    results: dict[str, str] = {}

    for view_name in views:
        output_path = out_dir / f"{view_name}.png"
        shutil.copy2(input_path, output_path)
        results[view_name] = str(output_path)
        if on_progress:
            on_progress(view_name, "fallback")

    return results

