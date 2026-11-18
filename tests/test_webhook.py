"""Tests for the play webhook's token resolution logic."""

import importlib
import sys
import types
import unittest
from pathlib import Path

package = types.ModuleType("yujian_webhook_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "yujian")
]
sys.modules[package.__name__] = package
webhook = importlib.import_module("yujian_webhook_test.webhook")


class ResolveRuntimeTests(unittest.TestCase):
    def test_resolves_by_token(self):
        runtime = {"callback_token": "abc"}
        data = {"entry1": runtime, "_flag": True}
        self.assertIs(webhook.resolve_runtime("abc", data), runtime)

    def test_rejects_wrong_token(self):
        data = {"entry1": {"callback_token": "abc"}}
        self.assertIsNone(webhook.resolve_runtime("xyz", data))

    def test_rejects_missing_or_empty_token(self):
        data = {"entry1": {"callback_token": "abc"}}
        self.assertIsNone(webhook.resolve_runtime(None, data))
        self.assertIsNone(webhook.resolve_runtime("", data))

    def test_empty_data(self):
        self.assertIsNone(webhook.resolve_runtime("abc", {}))

    def test_validate_track_id(self):
        self.assertEqual(webhook.validate_track_id(None), (True, None))
        self.assertEqual(webhook.validate_track_id("  "), (True, None))
        self.assertEqual(
            webhook.validate_track_id(" library://track/12 "),
            (True, "library://track/12"),
        )
        self.assertEqual(
            webhook.validate_track_id("spotify://track/abc"),
            (True, "spotify://track/abc"),
        )
        self.assertEqual(webhook.validate_track_id(123), (False, None))
        self.assertEqual(webhook.validate_track_id("not-a-uri"), (False, None))


if __name__ == "__main__":
    unittest.main()
