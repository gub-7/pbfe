"""Multi-view image generation using OpenAI's image generation API.

Given a single corner-angle photo, generates the 5 canonical views
(front, back, left, right, top) needed for 3D reconstruction.

Camera coordinate convention (matches gpu-cluster/pipelines/canonical_mv):
    - World space: Y-up, right-handed
    - Subject centered at origin (0, 0, 0)
    - Camera distance: 2.5 units from origin
    - front:  camera at (0, 0, +2.5)  — looking along -Z
    - right:  camera at (+2.5, 0, 0)  — looking along -X
    - back:   camera at (0, 0, -2.5)  — looking along +Z
    - left:   camera at (-2.5, 0, 0)  — looking along +X
    - top:    camera at (0, +2.5, 0)  — looking straight down along -Y
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

# ─────────────────────────────────────────────────────────────────────
# Shared preamble injected into every view prompt.
# Establishes the rules that the AI must follow across all views.
# ─────────────────────────────────────────────────────────────────────
_SHARED_PREAMBLE = (
    "You are generating one view of a multi-view orthographic reference sheet "
    "for 3D reconstruction. The following rules are CRITICAL and must be obeyed:\n\n"
    "1. SAME OBJECT — The subject must be the EXACT same object as the input image. "
    "Preserve every detail: shape, proportions, colors, textures, markings, and materials.\n"
    "2. CONSISTENT POSE — The object does NOT move or rotate. Only the camera moves. "
    "The object stays in the exact same pose/orientation as the input image.\n"
    "3. CENTERED — The subject must be perfectly centered in the frame, both horizontally and vertically.\n"
    "4. FILL FRAME — The subject should occupy approximately 60-70% of the image width and height. "
    "Maintain the same apparent size across all views.\n"
    "5. PURE WHITE BACKGROUND — The background must be perfectly uniform white (#FFFFFF). "
    "No gradients, no shadows, no reflections, no floor, no environment.\n"
    "6. FLAT LIGHTING — Use perfectly even, diffuse lighting with no cast shadows, "
    "no specular highlights, and no ambient occlusion. The object should look like "
    "a product photo on a white cyclorama.\n"
    "7. NO PERSPECTIVE DISTORTION — Use a long telephoto / near-orthographic projection. "
    "Parallel lines on the object must remain parallel in the image.\n\n"
)

VIEW_PROMPTS = {
    "front": (
        _SHARED_PREAMBLE +
        "CAMERA POSITION: The camera is placed directly in front of the subject, "
        "at coordinates (0, 0, +2.5) in a Y-up right-handed coordinate system. "
        "The camera looks straight at the subject along the -Z axis.\n\n"
        "This is a perfectly straight-on FRONT view. The camera is at the same height "
        "as the center of the subject (eye level). You should see the front face of the "
        "object filling the frame, with equal amounts of space on all sides. "
        "No part of the left side, right side, top surface, or back should be visible — "
        "the view is perfectly perpendicular to the front face."
    ),
    "back": (
        _SHARED_PREAMBLE +
        "CAMERA POSITION: The camera is placed directly behind the subject, "
        "at coordinates (0, 0, -2.5) in a Y-up right-handed coordinate system. "
        "The camera looks straight at the back of the subject along the +Z axis.\n\n"
        "This is a perfectly straight-on BACK view. The camera is at the same height "
        "as the center of the subject (eye level). You should see the back/rear face of the "
        "object filling the frame. This is exactly the opposite of the front view — "
        "as if you walked around to the other side. "
        "No part of the left side, right side, top surface, or front should be visible — "
        "the view is perfectly perpendicular to the back face."
    ),
    "left": (
        _SHARED_PREAMBLE +
        "CAMERA POSITION: The camera is placed directly to the LEFT of the subject, "
        "at coordinates (-2.5, 0, 0) in a Y-up right-handed coordinate system. "
        "The camera looks straight at the left side of the subject along the +X axis.\n\n"
        "This is a perfectly straight-on LEFT SIDE view. The camera is at the same height "
        "as the center of the subject (eye level). You should see the left side profile of the "
        "object filling the frame. "
        "No part of the front, back, right side, or top surface should be visible — "
        "the view is perfectly perpendicular to the left face."
    ),
    "right": (
        _SHARED_PREAMBLE +
        "CAMERA POSITION: The camera is placed directly to the RIGHT of the subject, "
        "at coordinates (+2.5, 0, 0) in a Y-up right-handed coordinate system. "
        "The camera looks straight at the right side of the subject along the -X axis.\n\n"
        "This is a perfectly straight-on RIGHT SIDE view. The camera is at the same height "
        "as the center of the subject (eye level). You should see the right side profile of the "
        "object filling the frame. This is exactly the mirror of the left view. "
        "No part of the front, back, left side, or top surface should be visible — "
        "the view is perfectly perpendicular to the right face."
    ),
    "top": (
        _SHARED_PREAMBLE +
        "CAMERA POSITION: The camera is placed directly ABOVE the subject, "
        "at coordinates (0, +2.5, 0) in a Y-up right-handed coordinate system. "
        "The camera points straight down along the -Y axis.\n\n"
        "This is a perfectly straight-down TOP / BIRD'S-EYE view. "
        "You are looking directly down at the top surface of the object. "
        "The front of the object should face toward the bottom of the image. "
        "You should see only the top surface — no front, back, left, or right sides "
        "should be visible. The view is perfectly perpendicular to the top surface, "
        "as if the object is lying on a table and you are hovering directly above it."
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
        Dict mapping view name -> file path.
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
