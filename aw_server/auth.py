"""
Optional API key authentication for /api/* endpoints.

When ``api_key`` is set under ``[server.auth]`` in aw-server.toml, every request to
``/api/*`` must carry an ``Authorization: Bearer <key>`` header, except:

- ``GET /api/0/info`` — health/version endpoint used by clients and the web UI
- ``OPTIONS`` requests — CORS preflight, must succeed before credentials can be sent

All other protected requests with a missing or wrong key receive 401 Unauthorized.
Static-file paths (non-``/api``) are always public.

Path matching uses split segments so both double-slash (``//api/0/buckets/``) and
percent-encoded (``/%61pi/0/buckets/``) bypass attempts are defeated: Werkzeug
delivers a percent-decoded path, and empty-segment filtering removes double slashes,
so the segment list always matches what the router dispatches to.
"""

import hmac
import logging
from typing import List, Optional

from flask import Flask, Response, request

logger = logging.getLogger(__name__)

# Path segments that are always public even when auth is enabled.
_PUBLIC_SEGMENTS: List[List[str]] = [["api", "0", "info"]]


def register(app: Flask, api_key: Optional[str]) -> None:
    """Register the API-key ``before_request`` hook on *app*.

    Calling with *api_key* as ``None`` or an empty string is a no-op:
    no hook is registered and authentication stays disabled.
    """
    if not api_key:
        return

    @app.before_request
    def _check_api_key() -> Optional[Response]:
        # CORS preflight — must pass through so the browser can obtain
        # allowed headers before sending the credentialled request.
        if request.method == "OPTIONS":
            return None

        # Build the canonical segment list once: percent-decoding is already
        # done by Werkzeug; filtering empty strings collapses double slashes.
        segments = [s for s in request.path.split("/") if s]

        # Only /api/* is gated; static files and other paths are public.
        if not segments or segments[0] != "api":
            return None

        # Public API paths bypass the key check (read-only: GET only).
        if request.method == "GET" and segments in _PUBLIC_SEGMENTS:
            return None

        auth_header = request.headers.get("Authorization", "")
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token:
            # UTF-8 on both sides: compare_digest needs matching encodings, and
            # ASCII would raise UnicodeEncodeError for a non-ASCII configured
            # key, locking out even the correct token. UTF-8 never raises on str.
            if hmac.compare_digest(token.encode("utf-8"), api_key.encode("utf-8")):
                return None

        return Response(
            '{"message": "Missing or invalid API key. Set Authorization: Bearer <key> header."}',
            status=401,
            content_type="application/json",
        )
