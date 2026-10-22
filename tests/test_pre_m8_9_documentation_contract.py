from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from storage.schema import CURRENT_SCHEMA_VERSION  # noqa: E402


class PreM89DocumentationContractTests(unittest.TestCase):
    def test_readme_describes_current_user_and_release_contracts(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("KOLConnect 采用本地优先设计", readme)
        self.assertIn("主要业务数据保存在你的电脑上", readme)
        self.assertIn("KOLConnect_v2.0.1_Windows_x64.zip", readme)
        self.assertIn("KOLConnect_v2.0.1_macOS_arm64.dmg", readme)
        self.assertIn("KOLConnect_Chrome_Extension_v2.0.1.zip", readme)

    def test_readme_does_not_advertise_retired_or_unsupported_contracts(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("TikTok Passive Capture V2", readme)
        self.assertIn("尚不是正式生产功能", readme)
        self.assertIn("不支持 Outlook / Microsoft 365 邮箱", readme)
        self.assertIn("不会猜测或伪造缺失数据", readme)

    def test_canonical_feishu_setup_matches_current_chat_contract(self) -> None:
        setup = (ROOT / "docs" / "feishu_setup.md").read_text(encoding="utf-8")
        self.assertIn("长连接", setup)
        self.assertIn("im.message.receive_v1", setup)
        self.assertIn("im:message:send_as_bot", setup)
        self.assertIn("验证连接", setup)
        self.assertIn("预检查 / Dry Run", setup)
        self.assertIn("同步到飞书", setup)

    def test_legacy_feishu_and_openclaw_material_is_marked_reference_only(self) -> None:
        legacy = (ROOT / "docs" / "飞书集成配置指南.md").read_text(encoding="utf-8")
        openclaw = (ROOT / "docs" / "feishu-openclaw-skill.md").read_text(encoding="utf-8")
        self.assertIn("HISTORICAL / REFERENCE-ONLY", legacy)
        self.assertIn("DEPRECATED / HISTORICAL / REFERENCE-ONLY", openclaw)


if __name__ == "__main__":
    unittest.main()
