"""Webhook that receives "play this playlist" requests from the TV."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.http import HomeAssistantView

from .const import CONF_MODEL, DOMAIN, PLAY_WEBHOOK_PATH

_LOGGER = logging.getLogger(__name__)

# Error text the TV shows in its toast, so the user learns what to fix.
NO_TARGET_ERROR = (
    "未指定目标播放器：请在玉简集成「配置 → 目标播放器」里选择这台电视对应的"
    " Music Assistant 播放器"
)


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

        from .media import async_play_playlist, find_owned_player

        # Who asked decides where it plays. Never fall back to "the first Music
        # Assistant player": with several players around (phone, sound box, sync
        # group) that plays the right playlist in the wrong room.
        asked_model = (body or {}).get("model")
        entry = runtime.get("entry")
        entry_model = entry.data.get(CONF_MODEL) if entry is not None else None
        entity_id = (
            runtime.get("target_entity_id")
            or find_owned_player(
                self._hass, asked_model if isinstance(asked_model, str) else None
            )
            or find_owned_player(self._hass, entry_model)
        )
        if not entity_id:
            _LOGGER.warning(
                "%s 请求播放歌单，但无法确定对应的 Music Assistant 播放器；"
                "请在玉简集成配置里选择「目标播放器」",
                entry.title if entry is not None else "电视",
            )
            return self.json({"ok": False, "error": NO_TARGET_ERROR}, status_code=409)

        try:
            await async_play_playlist(self._hass, entity_id, uri)
        except Exception as err:  # noqa: BLE001 - report failures to the TV
            _LOGGER.warning("播放歌单 %s 失败（%s）: %s", uri, entity_id, err)
            return self.json({"ok": False, "error": str(err)}, status_code=500)
        return self.json({"ok": True, "entity_id": entity_id})
