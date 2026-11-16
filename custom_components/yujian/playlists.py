"""Build the playlist-catalog payload pushed to the TV.

This module stays free of Home Assistant imports so its logic can be unit
tested in isolation; it only assembles plain dicts.
"""

from __future__ import annotations

from typing import Any

# Schema version of the /library payload; the TV app can reject unknown ones.
PAYLOAD_VERSION = 1


def playlist_item(
    name: str,
    media_id: str,
    cover_b64: str | None = None,
    track_count: int | None = None,
) -> dict[str, Any]:
    """Turn one playlist into the dict the TV expects.

    ``cover_b64`` is a ``data:image/...;base64,...`` string or None.
    """
    item: dict[str, Any] = {"id": media_id, "name": name}
    if cover_b64:
        item["cover_b64"] = cover_b64
    if track_count is not None:
        item["track_count"] = track_count
    return item


def build_playlists_payload(
    playlists: list[dict[str, Any]],
    callback: dict[str, Any],
    target_entity_id: str | None,
) -> dict[str, Any]:
    """Assemble the complete /library payload."""
    return {
        "version": PAYLOAD_VERSION,
        "target_entity_id": target_entity_id or "",
        "callback": callback,
        "playlists": playlists,
    }


def fingerprint(playlists: list[dict[str, Any]]) -> tuple[tuple[str, Any], ...]:
    """Return a stable identity of the catalog so unchanged lists skip re-push."""
    return tuple(sorted((item.get("id"), item.get("name")) for item in playlists))
