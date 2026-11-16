"""Tests for the pure playlist payload builder (no Home Assistant needed)."""

import importlib
import sys
import types
import unittest
from pathlib import Path

package = types.ModuleType("yujian_playlists_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "yujian")
]
sys.modules[package.__name__] = package
playlists = importlib.import_module("yujian_playlists_test.playlists")


class PlaylistPayloadTests(unittest.TestCase):
    def test_item_includes_optional_fields(self):
        item = playlists.playlist_item(
            "我的歌单",
            "library://playlist/13",
            cover_b64="data:image/jpeg;base64,AA",
            track_count=42,
        )
        self.assertEqual(
            item,
            {
                "id": "library://playlist/13",
                "name": "我的歌单",
                "cover_b64": "data:image/jpeg;base64,AA",
                "track_count": 42,
            },
        )

    def test_item_omits_empty_cover_and_none_count(self):
        item = playlists.playlist_item("x", "library://playlist/1")
        self.assertEqual(item, {"id": "library://playlist/1", "name": "x"})

    def test_payload_shape(self):
        payload = playlists.build_playlists_payload(
            [{"id": "library://playlist/1", "name": "x"}],
            {"url": "http://ha/api/yujian/play", "token": "t"},
            "media_player.music_assistant_x",
        )
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["target_entity_id"], "media_player.music_assistant_x")
        self.assertEqual(payload["callback"]["token"], "t")
        self.assertEqual(len(payload["playlists"]), 1)

    def test_fingerprint_is_order_insensitive(self):
        a = [
            {"id": "library://playlist/1", "name": "x"},
            {"id": "library://playlist/2", "name": "y"},
        ]
        b = [
            {"id": "library://playlist/2", "name": "y"},
            {"id": "library://playlist/1", "name": "x"},
        ]
        self.assertEqual(playlists.fingerprint(a), playlists.fingerprint(b))

    def test_fingerprint_changes_with_content(self):
        a = [{"id": "library://playlist/1", "name": "x"}]
        b = [{"id": "library://playlist/1", "name": "renamed"}]
        self.assertNotEqual(playlists.fingerprint(a), playlists.fingerprint(b))


if __name__ == "__main__":
    unittest.main()
