"""Build the playlist-catalog payload pushed to the TV.

This module stays free of Home Assistant imports so its logic can be unit
tested in isolation; it only assembles plain dicts.
"""

from __future__ import annotations

import json
from typing import Any

# Schema version of the /library payload; the TV app can reject unknown ones.
PAYLOAD_VERSION = 1

# The TV refuses a request body larger than 4 MB; keep a margin for the JSON
# envelope so a big catalog still lands.
MAX_PAYLOAD_BYTES = 3_500_000


def track_item(
    name: str,
    media_id: str,
    artist: str | None = None,
) -> dict[str, Any]:
    """Turn one track into the compact dict the TV expects."""
    item: dict[str, Any] = {"id": media_id, "name": name}
    if artist:
        item["artist"] = artist
    return item


def playlist_item(
    name: str,
    media_id: str,
    cover_b64: str | None = None,
    track_count: int | None = None,
    tracks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Turn one playlist into the dict the TV expects.

    ``cover_b64`` is a ``data:image/...;base64,...`` string or None.
    """
    item: dict[str, Any] = {"id": media_id, "name": name}
    if cover_b64:
        item["cover_b64"] = cover_b64
    if tracks is not None:
        item["tracks"] = tracks
        if track_count is None:
            track_count = len(tracks)
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


def fingerprint(playlists: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    """Return a stable identity of the catalog so unchanged lists skip re-push."""
    return tuple(
        sorted(
            (
                item.get("id"),
                item.get("name"),
                tuple(track.get("id") for track in (item.get("tracks") or ())),
            )
            for item in playlists
        )
    )


def payload_bytes(payload: dict[str, Any]) -> int:
    """Return the UTF-8 size of the serialized payload."""
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


MAX_TRACKS_PER_PLAYLIST = 150


def fit_payload(
    playlists: list[dict[str, Any]],
    callback: dict[str, Any],
    target_entity_id: str | None,
    limit: int = MAX_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Build the /library payload, dropping covers (then trimming/dropping tracks) if too big.

    Covers are the heaviest field; if even a coverless catalog with huge track
    lists exceeds the TV's limit, tracks are trimmed first (preserving total
    track_count) and dropped only as a last resort so the catalog still lands.
    """
    payload = build_playlists_payload(playlists, callback, target_entity_id)
    if payload_bytes(payload) <= limit:
        return payload
    no_covers = [
        {key: value for key, value in item.items() if key != "cover_b64"}
        for item in playlists
    ]
    payload = build_playlists_payload(no_covers, callback, target_entity_id)
    if payload_bytes(payload) <= limit:
        return payload
    trimmed = [
        {
            **item,
            "tracks": item["tracks"][:MAX_TRACKS_PER_PLAYLIST],
            "track_count": item.get("track_count", len(item["tracks"])),
        }
        if isinstance(item.get("tracks"), list)
        and len(item["tracks"]) > MAX_TRACKS_PER_PLAYLIST
        else item
        for item in no_covers
    ]
    payload = build_playlists_payload(trimmed, callback, target_entity_id)
    if payload_bytes(payload) <= limit:
        return payload
    lightweight = [
        {key: value for key, value in item.items() if key != "tracks"}
        for item in no_covers
    ]
    return build_playlists_payload(lightweight, callback, target_entity_id)
