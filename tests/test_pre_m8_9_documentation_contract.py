from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PreM89DocumentationContractTests(unittest.TestCase):
    def test_readme_describes_current_authority_and_release_contracts(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("SQLite 是当前应用数据权威", readme)
        self.assertIn("kolconnect.db", readme)
        self.assertIn("schema version 为 **3**", readme)
        self.assertIn("ONEDIR + ZIP", readme)
        self.assertIn("python scripts/run_python_tests.py --verbosity 1", readme)
        self.assertIn("python -m unittest discover", readme)

    def test_readme_does_not_advertise_retired_or_unsupported_contracts(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("TikTok Passive Capture V2", readme)
        self.assertIn("不是当前生产功能", readme)
        self.assertIn("OpenClaw 不是当前运行时依赖", readme)
        self.assertIn("Microsoft Outlook / Microsoft 365", readme)
        self.assertIn("不属于官方支持范围", readme)
        self.assertIn("混合币种金额绝不会被静默", readme)

    def test_canonical_feishu_setup_matches_current_chat_contract(self) -> None:
        setup = (ROOT / "docs" / "feishu_setup.md").read_text(encoding="utf-8")
        self.assertIn("official lark-oapi SDK long connection", setup)
        self.assertIn("No public callback or webhook URL is required", setup)
        self.assertIn("im.message.receive_v1", setup)
        self.assertIn("im:message:send_as_bot", setup)
        self.assertIn("Settings -> Validate -> Dry Run -> confirmed Full Sync", setup)

    def test_legacy_feishu_and_openclaw_material_is_marked_reference_only(self) -> None:
        legacy = (ROOT / "docs" / "飞书集成配置指南.md").read_text(encoding="utf-8")
        openclaw = (ROOT / "docs" / "feishu-openclaw-skill.md").read_text(encoding="utf-8")
        self.assertIn("HISTORICAL / REFERENCE-ONLY", legacy)
        self.assertIn("DEPRECATED / HISTORICAL / REFERENCE-ONLY", openclaw)


if __name__ == "__main__":
    unittest.main()
