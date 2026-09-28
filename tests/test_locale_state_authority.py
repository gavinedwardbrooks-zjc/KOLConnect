from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import server
from http_handlers.settings_handler import _normalize_ui_language


class LocaleStateAuthorityTests(unittest.TestCase):
    def test_legacy_ui_locale_forms_normalize_without_touching_domain_language(self) -> None:
        for value in ("en", "en-US", "English"):
            self.assertEqual("en", server.normalize_state({"ui": {"language": value}})["ui"]["language"])
            self.assertEqual("en", _normalize_ui_language(value))
        for value in ("zh", "zh-CN", "Chinese", "中文", "unknown"):
            self.assertEqual("zh", server.normalize_state({"ui": {"language": value}})["ui"]["language"])
            self.assertEqual("zh", _normalize_ui_language(value))


if __name__ == "__main__":
    unittest.main()
