from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CURRENT_VERSION = "1.0.0"


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

        windows_metadata = (ROOT / "packaging" / "windows_version_info.txt").read_text(
            encoding="utf-8-sig"
        )
        windows_installer = (ROOT / "packaging" / "installer" / "KOLConnect.iss").read_text(
            encoding="utf-8-sig"
        )
        windows_spec = (ROOT / "packaging" / "spec" / "KOLConnect.spec").read_text(
            encoding="utf-8-sig"
        )
        mac_arm_spec = (ROOT / "packaging" / "spec" / "KOLConnect_mac.spec").read_text(
            encoding="utf-8-sig"
        )
        mac_intel_spec = (ROOT / "packaging" / "spec" / "KOLConnect_mac_intel.spec").read_text(
            encoding="utf-8-sig"
        )
        extension_schema = (ROOT / "chrome_extension" / "core" / "schema.js").read_text(
            encoding="utf-8"
        )
        extension_ui = (ROOT / "chrome_extension" / "content" / "floating_assistant.js").read_text(
            encoding="utf-8"
        )
        web_index = (ROOT / "webapp" / "index.html").read_text(encoding="utf-8")
        web_app = (ROOT / "webapp" / "app.js").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(f'RELEASE_NAME = "KOLConnect_v{CURRENT_VERSION}"', windows_spec)
        self.assertIn(f"KOLConnect v{CURRENT_VERSION}", windows_metadata)
        self.assertIn(f"'{CURRENT_VERSION}.0'", windows_metadata)
        self.assertIn(f'#define AppVersion "{CURRENT_VERSION}"', windows_installer)
        self.assertIn(f"KOLConnect_v{CURRENT_VERSION}.exe", windows_installer)
        for spec in (mac_arm_spec, mac_intel_spec):
            self.assertIn(f'"CFBundleShortVersionString": "{CURRENT_VERSION}"', spec)
            self.assertIn(f'"CFBundleVersion": "{CURRENT_VERSION}"', spec)
        self.assertIn(f'EXTENSION_VERSION = "v{CURRENT_VERSION}"', extension_schema)
        self.assertIn(f"KOLConnect v{CURRENT_VERSION}", extension_ui)
        self.assertIn(f"KOLConnect v{CURRENT_VERSION}", web_index)
        self.assertIn(f"KOLConnect v{CURRENT_VERSION}", web_app)
        self.assertIn(f"KOLConnect_v{CURRENT_VERSION}.zip", readme)

        artifacts = (
            f"KOLConnect_v{CURRENT_VERSION}.zip",
            f"KOLConnect_v{CURRENT_VERSION}_mac_arm64.dmg",
            f"KOLConnect_v{CURRENT_VERSION}_mac_intel.dmg",
        )
        for artifact in artifacts:
            self.assertIn(artifact, workflow)

        self.assertIn('RELEASE_FORMAT = ONEDIR', windows_build)
        self.assertIn('$releaseDirectory', windows_build)
        self.assertIn('$releaseZip', windows_build)

        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("merge-multiple: true", workflow)
        self.assertIn("files: release-assets/*", workflow)
        self.assertIn("- build-windows", workflow)
        self.assertIn("- build-macos-arm64", workflow)
        self.assertIn("- build-macos-intel", workflow)


if __name__ == "__main__":
    unittest.main()
