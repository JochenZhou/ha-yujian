"""Tests for MA browse/play wrappers using a mock Home Assistant."""

import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

package = types.ModuleType("yujian_media_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "yujian")
]
sys.modules[package.__name__] = package
media = importlib.import_module("yujian_media_test.media")


class FakeState:
    def __init__(self, state="idle", friendly_name=None):
        self.state = state
        self.attributes = {"friendly_name": friendly_name} if friendly_name else {}


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


def _entry(entity_id, platform="music_assistant", domain="media_player", **kwargs):
    return SimpleNamespace(
        entity_id=entity_id,
        domain=domain,
        platform=platform,
        disabled_by=kwargs.get("disabled_by"),
        hidden_by=kwargs.get("hidden_by"),
    )


def _states(*pairs):
    return {entity_id: FakeState(state) for entity_id, state in pairs}


class FindPlayerTests(unittest.TestCase):
    def test_detects_players_by_registry_platform(self):
        """MA entity ids carry no fixed prefix; the registry decides."""
        hass = _hass(entities=_states(
            ("media_player.ke_ting_akubox", "idle"),
            ("media_player.spotify_x", "idle"),
        ))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.ke_ting_akubox"),
            _entry("media_player.spotify_x", platform="spotify"),
        ]):
            self.assertEqual(
                media.find_mass_player(hass), "media_player.ke_ting_akubox"
            )

    def test_prefers_available_player(self):
        hass = _hass(entities=_states(
            ("media_player.a_box", "unavailable"),
            ("media_player.b_box", "idle"),
        ))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.a_box"),
            _entry("media_player.b_box"),
        ]):
            self.assertEqual(media.find_mass_player(hass), "media_player.b_box")

    def test_preferred_kept_even_when_unavailable(self):
        """A standby TV must stay the play target."""
        hass = _hass(entities=_states(
            ("media_player.tv", "unavailable"),
            ("media_player.box", "idle"),
        ))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.tv"),
            _entry("media_player.box"),
        ]):
            self.assertEqual(
                media.find_mass_player(hass, "media_player.tv"), "media_player.tv"
            )

    def test_browse_player_skips_unavailable_preferred(self):
        hass = _hass(entities=_states(
            ("media_player.tv", "unavailable"),
            ("media_player.box", "idle"),
        ))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.tv"),
            _entry("media_player.box"),
        ]):
            self.assertEqual(
                media.find_browse_player(hass, "media_player.tv"), "media_player.box"
            )

    def test_browse_player_none_when_all_offline(self):
        hass = _hass(entities=_states(("media_player.tv", "unavailable")))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.tv"),
        ]):
            self.assertIsNone(media.find_browse_player(hass, "media_player.tv"))

    def test_skips_disabled_and_hidden(self):
        hass = _hass(entities=_states(
            ("media_player.off", "idle"),
            ("media_player.hidden", "idle"),
            ("media_player.on", "idle"),
        ))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.off", disabled_by="user"),
            _entry("media_player.hidden", hidden_by="user"),
            _entry("media_player.on"),
        ]):
            self.assertEqual(media.find_mass_player(hass), "media_player.on")

    def test_legacy_prefix_fallback_without_registry(self):
        hass = _hass(entities=_states(
            ("media_player.music_assistant_a", "idle"),
            ("media_player.other", "idle"),
        ))
        with patch.object(media, "registry_entries", side_effect=RuntimeError("no reg")):
            self.assertEqual(
                media.find_mass_player(hass), "media_player.music_assistant_a"
            )

    def test_none_when_no_mass_player(self):
        hass = _hass(entities=_states(("media_player.sonos", "idle")))
        with patch.object(media, "registry_entries", return_value=[]):
            self.assertIsNone(media.find_mass_player(hass))


class OwnedPlayerTests(unittest.TestCase):
    """The TV that asked must decide where its playlist plays."""

    def test_matches_entity_by_model_with_punctuation(self):
        hass = _hass(entities=_states(("media_player.yu_jian_mitv4_ansm0", "idle")))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.yu_jian_mitv4_ansm0"),
        ]):
            self.assertEqual(
                media.find_owned_player(hass, "MiTV4-ANSM0"),
                "media_player.yu_jian_mitv4_ansm0",
            )

    def test_does_not_pick_other_players(self):
        """A sound box in another room must never be chosen for a TV."""
        hass = _hass(entities=_states(
            ("media_player.akubox", "idle"),
            ("media_player.yu_jian_tb371fc", "idle"),
        ))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.akubox"),
            _entry("media_player.yu_jian_tb371fc"),
        ]):
            self.assertEqual(
                media.find_owned_player(hass, "TB371FC"), "media_player.yu_jian_tb371fc"
            )

    def test_returns_none_when_no_player_matches(self):
        hass = _hass(entities=_states(("media_player.akubox", "idle")))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.akubox"),
        ]):
            self.assertIsNone(media.find_owned_player(hass, "TB371FC"))

    def test_ignores_short_or_empty_model(self):
        hass = _hass(entities=_states(("media_player.yu_jian_tv", "idle")))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.yu_jian_tv"),
        ]):
            self.assertIsNone(media.find_owned_player(hass, "TV"))
            self.assertIsNone(media.find_owned_player(hass, ""))
            self.assertIsNone(media.find_owned_player(hass, None))

    def test_prefers_available_twin(self):
        hass = _hass(entities=_states(
            ("media_player.yu_jian_mitv4_ansm0", "unavailable"),
            ("media_player.yu_jian_mitv4_ansm0_2", "idle"),
        ))
        with patch.object(media, "registry_entries", return_value=[
            _entry("media_player.yu_jian_mitv4_ansm0"),
            _entry("media_player.yu_jian_mitv4_ansm0_2"),
        ]):
            self.assertEqual(
                media.find_owned_player(hass, "MiTV4-ANSM0"),
                "media_player.yu_jian_mitv4_ansm0_2",
            )


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
                return {"media_player.a": root}
            return {"media_player.a": listing}

        hass = _hass(entities=_states(("media_player.a", "idle")))
        hass.services.async_call.side_effect = fake_call
        result = await media.async_list_playlists(hass, "media_player.a")
        self.assertEqual(
            result,
            [{"id": "library://playlist/1", "name": "歌单A", "thumbnail": "http://x/c.jpg"}],
        )

    async def test_play_playlist_uses_standard_service(self):
        hass = _hass()
        await media.async_play_playlist(
            hass, "media_player.a", "library://playlist/1"
        )
        args, kwargs = hass.services.async_call.call_args
        self.assertEqual(args[0], "media_player")
        self.assertEqual(args[1], "play_media")
        self.assertEqual(
            args[2],
            {
                "entity_id": "media_player.a",
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

    async def test_cover_cache_avoids_refetch(self):
        playlists = [
            {"id": "library://playlist/1", "name": "a", "thumbnail": "http://x/1.jpg"},
        ]
        cache = {"library://playlist/1": "data:image/jpeg;base64,AA"}
        with patch.object(media, "async_fetch_cover_b64", new_callable=AsyncMock) as fetch:
            items = await media.fetch_covers(_hass(), playlists, cache)
        fetch.assert_not_called()
        self.assertEqual(items[0]["cover_b64"], "data:image/jpeg;base64,AA")

    async def test_cover_is_shrunk_to_small_jpeg(self):
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (1600, 1600), (200, 30, 30)).save(buffer, format="PNG")
        big = buffer.getvalue()

        class Response:
            status = 200
            headers = {"Content-Type": "image/png"}

            def __init__(self, data):
                self._data = data

            async def read(self):
                return self._data

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class Session:
            def get(self, url, timeout=None):
                return Response(big)

        hass = _hass()
        with patch.object(media, "clients_session", return_value=Session()):
            uri = await media.async_fetch_cover_b64(hass, "http://x/big.png")
        self.assertTrue(uri.startswith("data:image/jpeg;base64,"))
        self.assertLess(len(uri), len(big))
        self.assertLess(len(uri), 40_000)

    async def test_cover_cache_records_missing_cover(self):
        playlists = [
            {"id": "library://playlist/2", "name": "b", "thumbnail": None},
        ]
        cache = {}
        items = await media.fetch_covers(_hass(), playlists, cache)
        self.assertNotIn("cover_b64", items[0])
        self.assertIn("library://playlist/2", cache)
        self.assertIsNone(cache["library://playlist/2"])


if __name__ == "__main__":
    unittest.main()
