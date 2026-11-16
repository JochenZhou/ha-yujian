"""Tests for MA browse/play wrappers using a mock Home Assistant."""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

package = types.ModuleType("yujian_media_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "yujian")
]
sys.modules[package.__name__] = package
media = importlib.import_module("yujian_media_test.media")


class FakeStates:
    def __init__(self, entities):
        self._entities = entities  # entity_id -> state object or None

    def async_entity_ids(self, domain):
        return [eid for eid in self._entities if eid.startswith(domain + ".")]

    def get(self, entity_id):
        return self._entities.get(entity_id)


def _hass(service_response=None, entities=None):
    hass = MagicMock()
    hass.services.async_call = AsyncMock(return_value=service_response)
    hass.states = FakeStates(entities or {})
    return hass


class FindPlayerTests(unittest.TestCase):
    def test_prefers_configured(self):
        hass = _hass(entities={
            "media_player.music_assistant_a": object(),
            "media_player.music_assistant_b": object(),
        })
        self.assertEqual(
            media.find_mass_player(hass, "media_player.music_assistant_b"),
            "media_player.music_assistant_b",
        )

    def test_skips_missing_and_sorts(self):
        hass = _hass(entities={
            "media_player.music_assistant_z": object(),
            "media_player.music_assistant_a": object(),
        })
        self.assertEqual(media.find_mass_player(hass), "media_player.music_assistant_a")

    def test_none_when_no_mass_player(self):
        hass = _hass(entities={"media_player.sonos": object()})
        self.assertIsNone(media.find_mass_player(hass))

    def test_none_when_preferred_gone(self):
        hass = _hass(entities={"media_player.sonos": object()})
        self.assertIsNone(media.find_mass_player(hass, "media_player.music_assistant_gone"))


class BrowsePlayTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_playlists_navigates_to_playlists_node(self):
        root = {
            "children": [
                {"media_content_id": "playlists", "media_content_type": "music_assistant"}
            ]
        }
        listing = {
            "children": [
                {
                    "media_content_id": "library://playlist/1",
                    "title": "歌单A",
                    "thumbnail": "http://x/c.jpg",
                },
                {"media_content_id": "spotify://playlist/x", "title": "跳过"},
            ]
        }

        async def fake_call(domain, service, data, **kwargs):
            if "media_content_id" not in data:
                return {"media_player.music_assistant_a": root}
            return {"media_player.music_assistant_a": listing}

        hass = _hass(entities={"media_player.music_assistant_a": object()})
        hass.services.async_call.side_effect = fake_call
        result = await media.async_list_playlists(hass, "media_player.music_assistant_a")
        self.assertEqual(
            result,
            [{"id": "library://playlist/1", "name": "歌单A", "thumbnail": "http://x/c.jpg"}],
        )

    async def test_play_playlist_uses_standard_service(self):
        hass = _hass()
        await media.async_play_playlist(
            hass, "media_player.music_assistant_a", "library://playlist/1"
        )
        args, kwargs = hass.services.async_call.call_args
        self.assertEqual(args[0], "media_player")
        self.assertEqual(args[1], "play_media")
        self.assertEqual(
            args[2],
            {
                "entity_id": "media_player.music_assistant_a",
                "media_content_id": "library://playlist/1",
                "media_content_type": "playlist",
                "enqueue": "replace",
            },
        )
        self.assertTrue(kwargs["blocking"])


class CoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_cover_skips_non_http_urls(self):
        self.assertIsNone(await media.async_fetch_cover_b64(_hass(), None))
        self.assertIsNone(await media.async_fetch_cover_b64(_hass(), ""))
        self.assertIsNone(await media.async_fetch_cover_b64(_hass(), "file:///x.jpg"))

    async def test_fetch_covers_attaches_cover_per_item(self):
        playlists = [
            {"id": "library://playlist/1", "name": "a", "thumbnail": "http://x/1.jpg"},
            {"id": "library://playlist/2", "name": "b", "thumbnail": None},
        ]

        async def fake_fetch(hass, url):
            return "data:image/jpeg;base64,AA" if url else None

        with patch.object(media, "async_fetch_cover_b64", side_effect=fake_fetch):
            items = await media.fetch_covers(_hass(), playlists)
        self.assertEqual(items[0]["cover_b64"], "data:image/jpeg;base64,AA")
        self.assertNotIn("cover_b64", items[1])


if __name__ == "__main__":
    unittest.main()
