"""Service Account credentials decoder.

Decodes ``GOOGLE_APPLICATION_CREDENTIALS_JSON`` (base64-encoded) at startup
into a JSON file at ``/tmp/sa-key.json``, enabling Vertex AI SDK auth in
production environments (Railway, Render, etc.) that don't have filesystem
persistence.

Local development uses ``GOOGLE_APPLICATION_CREDENTIALS`` as a path
directly — if that env var points to an existing file, this module
no-ops.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import structlog


log = structlog.get_logger(__name__)


SA_KEY_TARGET = "/tmp/sa-key.json"


def decode_service_account_credentials() -> str | None:
    """Resolve service-account credentials for the Vertex AI SDK.

    Resolution order:
      1. If ``GOOGLE_APPLICATION_CREDENTIALS`` already points to an
         existing file, use it as-is (local-dev path).
      2. Otherwise, look for ``GOOGLE_APPLICATION_CREDENTIALS_JSON``
         (base64 string), decode to ``/tmp/sa-key.json``, set
         ``GOOGLE_APPLICATION_CREDENTIALS`` to that path so the SDK
         picks it up via Application Default Credentials.
      3. Otherwise return None — caller assumes ADC will resolve via
         metadata server / `gcloud auth` / etc.

    Returns:
        Path to the credentials file in use, or None if neither env var
        is set. Never raises; logs and returns None on decode failure.
    """
    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing and Path(existing).exists():
        log.info("sa_credentials_local_file_exists", path=existing)
        return existing

    encoded = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not encoded:
        log.info(
            "sa_credentials_not_provided",
            note="local_dev_or_no_vertex",
        )
        return None

    try:
        # Railway / dashboard pastes sometimes include leading/trailing
        # whitespace or newlines that base64 won't tolerate.
        encoded = encoded.strip()
        decoded_bytes = base64.b64decode(encoded)

        try:
            json.loads(decoded_bytes)
        except json.JSONDecodeError as e:
            log.error("sa_credentials_invalid_json", error=str(e))
            return None

        target_path = Path(SA_KEY_TARGET)
        target_path.write_bytes(decoded_bytes)
        target_path.chmod(0o600)

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(target_path)

        log.info(
            "sa_credentials_decoded",
            target=str(target_path),
            size_bytes=len(decoded_bytes),
        )
        return str(target_path)

    except Exception as e:
        log.error("sa_credentials_decode_failed", error=str(e))
        return None
