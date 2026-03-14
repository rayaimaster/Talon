from __future__ import annotations

"""
Shared admin authentication helpers for operational endpoints.
"""

import logging
import os
from typing import Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


def require_admin_token(x_admin_token: Optional[str] = Header(default=None)) -> None:
    """Require a matching X-Admin-Token header for protected routes."""
    configured_token = os.environ.get("ADMIN_API_TOKEN", "").strip()
    if not configured_token:
        logger.error("ADMIN_API_TOKEN is not configured for protected admin routes")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_TOKEN is not configured on the server.",
        )

    if x_admin_token != configured_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Admin-Token header.",
        )
