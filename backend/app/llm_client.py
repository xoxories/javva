"""Centralized Gemini client factory.

Returns a Vertex AI-backed `genai.Client` if `settings.use_vertex_ai` is
True, otherwise an aistudio.google.com Gemini API direct client. Lets the
rest of the codebase swap between the two via a single env var without
importing pydantic-ai or knowing about provider classes.

Why the migration matters:
  - The `$1000` GenAI Trial credit applies to Vertex AI billing, not to
    aistudio direct (Cloud Prepay vs aistudio direct are separate billing
    systems).
  - aistudio direct on a non-paid project caps at 20 requests/day for
    `gemini-2.5-*` models on the free tier.
  - Vertex AI uses Application Default Credentials — set up once via
    `gcloud auth application-default login`.
"""

from __future__ import annotations

import structlog
from google import genai

from app.config import settings


log = structlog.get_logger(__name__)

_client_instance: genai.Client | None = None


def get_genai_client() -> genai.Client:
    """Return the cached genai.Client (lazy-initialized on first call).

    Raises:
        ValueError: if settings indicate Vertex but `gcp_project_id` is
            unset, or aistudio direct but `gemini_api_key` is unset.
    """
    global _client_instance

    if _client_instance is not None:
        return _client_instance

    if settings.use_vertex_ai:
        if not settings.gcp_project_id:
            raise ValueError(
                "use_vertex_ai=True requires GCP_PROJECT_ID in .env"
            )
        _client_instance = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        log.info(
            "genai_client_initialized",
            provider="vertex_ai",
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
    else:
        if not settings.gemini_api_key:
            raise ValueError(
                "use_vertex_ai=False requires GEMINI_API_KEY in .env"
            )
        _client_instance = genai.Client(api_key=settings.gemini_api_key)
        log.info("genai_client_initialized", provider="aistudio_direct")

    return _client_instance
