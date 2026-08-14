from __future__ import annotations

from typing import Any


def safe_json(response) -> dict[str, Any]:
    """Best-effort JSON parse of a Locust/requests response; empty dict on failure."""
    try:
        return response.json()
    except ValueError:
        return {}
