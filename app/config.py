"""Configuration for the BrickedUp backend orchestrator."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration from environment variables."""

    # OpenAI / Image generation
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    IMAGE_GEN_MODEL: str = os.getenv("IMAGE_GEN_MODEL", "gpt-image-1")

    # GPU Cluster (5 views → 3D GLB)
    GPU_CLUSTER_URL: str = os.getenv("GPU_CLUSTER_URL", "http://localhost:8001")

    # Rubric (GLB → LEGO LDR)
    RUBRIC_URL: str = os.getenv("RUBRIC_URL", "http://localhost:8002")

    # Local storage
    DATA_DIR: str = os.getenv("DATA_DIR", "data")
    UPLOAD_DIR: str = os.path.join(DATA_DIR, "uploads")
    VIEWS_DIR: str = os.path.join(DATA_DIR, "views")
    MODELS_DIR: str = os.path.join(DATA_DIR, "models")
    OUTPUT_DIR: str = os.path.join(DATA_DIR, "output")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:8000",
    ).split(",")

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all storage directories."""
        for d in [cls.UPLOAD_DIR, cls.VIEWS_DIR, cls.MODELS_DIR, cls.OUTPUT_DIR]:
            Path(d).mkdir(parents=True, exist_ok=True)


config = Config()

