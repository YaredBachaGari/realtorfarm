from __future__ import annotations

import json
import mimetypes
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BLOB_API_URL = "https://vercel.com/api/blob"
DEFAULT_ENV_PATHS = ("/opt/data/.env", "/docker/hermes-agent-irpn/data/.env")
DEFAULT_STORE_ID = "store_UqbIA72ov0PUTTqT"


class BlobUploadError(RuntimeError):
    """Raised when Vercel Blob upload fails."""


def load_env_value(name: str, *, env_paths: tuple[str, ...] = DEFAULT_ENV_PATHS) -> str:
    """Load an env value from process env or simple .env files without printing secrets.

    Supports both KEY=value and the nonstandard KEY value format used in this environment.
    """
    value = os.environ.get(name)
    if value:
        return value.strip().strip('"').strip("'")

    for env_path in env_paths:
        path = Path(env_path)
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
            if line.startswith(f"{name} "):
                return line.split(None, 1)[1].strip().strip('"').strip("'")
    return ""


def parse_store_id_from_token(token: str) -> str:
    """Return store id embedded in a Vercel Blob read-write token when visible."""
    import re

    match = re.search(r"store_[A-Za-z0-9]+", token)
    if match:
        return match.group(0)

    parts = token.split("_")
    if len(parts) >= 4 and parts[3]:
        return parts[3] if parts[3].startswith("store_") else f"store_{parts[3]}"
    return DEFAULT_STORE_ID


def upload_file_to_vercel_blob(
    file_path: str | Path,
    *,
    pathname: str,
    token: str | None = None,
    access: str = "private",
    allow_overwrite: bool = True,
    content_type: str | None = None,
    api_url: str = DEFAULT_BLOB_API_URL,
    store_id: str | None = None,
) -> dict[str, Any]:
    """Upload a local file to Vercel Blob and return the API response."""
    if access not in {"private", "public"}:
        raise ValueError("access must be 'private' or 'public'")

    token = token or load_env_value("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise BlobUploadError("BLOB_READ_WRITE_TOKEN is not set")

    path = Path(file_path)
    body = path.read_bytes()
    content_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    store_id = store_id or parse_store_id_from_token(token)

    params = urllib.parse.urlencode({"pathname": pathname})
    request = urllib.request.Request(
        f"{api_url}/?{params}",
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "x-content-type": content_type,
            "x-vercel-blob-access": access,
            "x-vercel-blob-store-id": store_id,
            "x-api-version": "12",
            "x-api-blob-request-attempt": "0",
            "x-api-blob-request-id": f"{store_id}:realtorfarm",
            "x-allow-overwrite": "1" if allow_overwrite else "0",
            "x-add-random-suffix": "0",
            "x-content-length": str(len(body)),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - exact urllib exception varies by Python version
        raise BlobUploadError(f"Vercel Blob upload failed for {pathname}: {exc}") from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BlobUploadError(f"Vercel Blob returned non-JSON response for {pathname}") from exc

    result.setdefault("pathname", pathname)
    return result
