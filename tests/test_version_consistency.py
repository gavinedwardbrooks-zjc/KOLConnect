from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = "0.2.3"


class VersionConsistencyTests(unittest.TestCase):
    def test_current_version_is_consistent_across_runtime_and_packaging(self):
        from app.version import APP_VERSION

        self.assertEqual(APP_VERSION, CURRENT_VERSION)

        manifest = json.loads(
            (ROOT / "chrome_extension" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], CURRENT_VERSION)
        self.assertEqual(manifest["version_name"], f"KOLConnect v{CURRENT_VERSION}")

        windows_build = (ROOT / "packaging" / "build_release.ps1").read_text(encoding="utf-8")
        macos_build = (ROOT / "packaging" / "build_macos.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")

        self.assertIn(f'$releaseVersion = "v{CURRENT_VERSION}"', windows_build)
        self.assertIn(f'VERSION="v{CURRENT_VERSION}"', macos_build)

        artifacts = (
            f"KOLConnect_v{CURRENT_VERSION}.exe",
            f"KOLConnect_v{CURRENT_VERSION}_mac_arm64.dmg",
            f"KOLConnect_v{CURRENT_VERSION}_mac_intel.dmg",
        )
        for artifact in artifacts:
            self.assertIn(artifact, workflow)

        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("merge-multiple: true", workflow)
        self.assertIn("files: release-assets/*", workflow)
        self.assertIn("- build-windows", workflow)
        self.assertIn("- build-macos-arm64", workflow)
        self.assertIn("- build-macos-intel", workflow)


if __name__ == "__main__":
    unittest.main()
