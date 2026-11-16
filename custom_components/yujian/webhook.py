"""Webhook that receives "play this playlist" requests from the TV."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN, PLAY_WEBHOOK_PATH

_LOGGER = logging.getLogger(__name__)


def resolve_runtime(token: str | None, data: dict[str, Any]) -> dict[str, Any] | None:
    """Map a bearer token to its config-entry runtime dict, or None.

    ``data`` is ``hass.data[DOMAIN]``, which maps entry ids to runtime dicts.
    Non-dict values (e.g. internal flags) are skipped so the lookup stays safe.
    """
    if not token:
        return None
    for runtime in data.values():
        if isinstance(runtime, dict) and runtime.get("callback_token") == token:
            return runtime
    return None


class YujianPlayView(HomeAssistantView):
    """Expose ``POST {PLAY_WEBHOOK_PATH}`` for the TV to start a playlist."""

    url = PLAY_WEBHOOK_PATH
    name = "api:yujian:play"
    requires_auth = False  # the TV authenticates with its per-entry token

    def __init__(self, hass) -> None:
        self._hass = hass

    async def post(self, request):
        """Handle a play request: validate token, then play the playlist."""
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        runtime = resolve_runtime(token, self._hass.data.get(DOMAIN, {}))
        if runtime is None:
            return self.json({"ok": False, "error": "unauthorized"}, status_code=401)

        try:
            body = await request.json()
        except ValueError:
            return self.json({"ok": False, "error": "invalid json"}, status_code=400)

        uri = (body or {}).get("id")
        if not isinstance(uri, str) or not uri.startswith("library://"):
            return self.json({"ok": False, "error": "invalid id"}, status_code=400)

        from .media import async_play_playlist, find_mass_player

        entity_id = runtime.get("target_entity_id") or find_mass_player(self._hass)
        if not entity_id:
            return self.json({"ok": False, "error": "no player"}, status_code=503)

        try:
            await async_play_playlist(self._hass, entity_id, uri)
        except Exception as err:  # noqa: BLE001 - report failures to the TV
            _LOGGER.warning("播放歌单 %s 失败: %s", uri, err)
            return self.json({"ok": False, "error": str(err)}, status_code=500)
        return self.json({"ok": True})
