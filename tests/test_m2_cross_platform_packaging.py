from __future__ import annotations

import ast
import importlib.metadata
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import runtime_paths


class RuntimePathTests(unittest.TestCase):
    def _app_data_dir(self, platform_name: str, home: Path, env: dict[str, str]) -> Path:
        with (
            mock.patch.object(runtime_paths.sys, "platform", platform_name),
            mock.patch.object(runtime_paths.Path, "home", return_value=home),
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(runtime_paths.Path, "mkdir") as mkdir,
        ):
            result = runtime_paths.get_app_data_dir()
        mkdir.assert_called_once_with(parents=True, exist_ok=True)
        return result

    def test_windows_uses_appdata(self):
        home = Path("C:/Users/test")
        base = home / "AppData" / "Roaming"
        result = self._app_data_dir("win32", home, {"APPDATA": str(base)})
        self.assertEqual(result, base / "KOLConnect")

    def test_macos_uses_application_support(self):
        home = Path("/Users/test")
        result = self._app_data_dir("darwin", home, {})
        self.assertEqual(result, home / "Library" / "Application Support" / "KOLConnect")

    def test_linux_uses_xdg_data_home(self):
        home = Path("/home/test")
        base = Path("/var/test-data")
        result = self._app_data_dir("linux", home, {"XDG_DATA_HOME": str(base)})
        self.assertEqual(result, base / "KOLConnect")

    def test_linux_falls_back_to_local_share(self):
        home = Path("/home/test")
        result = self._app_data_dir("linux", home, {})
        self.assertEqual(result, home / ".local" / "share" / "KOLConnect")


class PackagingConfigurationTests(unittest.TestCase):
    def test_pywebview_owns_darwin_pyobjc_dependencies(self):
        requirements = (ROOT / "packaging" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pywebview", requirements.lower())
        for line in requirements.splitlines():
            if line.strip().lower().startswith("pyobjc"):
                self.assertIn('sys_platform == "darwin"', line)

        pywebview_requirements = importlib.metadata.requires("pywebview") or []
        darwin_requirements = [item.lower() for item in pywebview_requirements if "darwin" in item.lower()]
        self.assertTrue(any("pyobjc-core" in item for item in darwin_requirements))
        self.assertTrue(any("pyobjc-framework-cocoa" in item for item in darwin_requirements))
        self.assertTrue(any("pyobjc-framework-webkit" in item for item in darwin_requirements))

    def test_specs_are_valid_python_and_keep_platform_backends_separate(self):
        windows_spec = (ROOT / "packaging" / "spec" / "KOLConnect.spec").read_text(encoding="utf-8")
        mac_spec = (ROOT / "packaging" / "spec" / "KOLConnect_mac.spec").read_text(encoding="utf-8")
        intel_spec = (ROOT / "packaging" / "spec" / "KOLConnect_mac_intel.spec").read_text(encoding="utf-8")
        ast.parse(windows_spec)
        ast.parse(mac_spec)
        ast.parse(intel_spec)
        for resource in ("webapp", "assets", "chrome_extension"):
            self.assertIn(resource, windows_spec)
            self.assertIn(resource, mac_spec)
            self.assertIn(resource, intel_spec)
        self.assertIn("webview.platforms.edgechromium", windows_spec)
        self.assertIn("windows_version_info.txt", windows_spec)
        self.assertIn("KOLConnect.ico", windows_spec)
        self.assertIn("webview.platforms.cocoa", mac_spec)
        self.assertIn("KOLConnect.icns", mac_spec)
        self.assertIn("KOLConnect.icns", intel_spec)
        self.assertNotIn("windows_version_info.txt", mac_spec)
        self.assertNotIn("windows_version_info.txt", intel_spec)
        self.assertIn('target_arch="arm64"', mac_spec)
        self.assertIn('target_arch="x86_64"', intel_spec)
        self.assertIn("collect_all(package_name)", intel_spec)

    def test_chromedriver_resolution_is_centralized_and_automatic(self):
        scraper_source = (APP_DIR / "scraper.py").read_text(encoding="utf-8")
        resolver_source = (APP_DIR / "chromedriver_resolver.py").read_text(encoding="utf-8")
        self.assertIn("resolve_chromedriver()", scraper_source)
        self.assertIn("ChromeDriverManager().install()", resolver_source)
        self.assertNotIn("find_local_chromedriver", scraper_source)

    def test_workflows_separate_validation_from_packaging(self):
        workflow_dir = ROOT / ".github" / "workflows"
        build = (workflow_dir / "build.yml").read_text(encoding="utf-8")
        ci = (workflow_dir / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", ci)
        self.assertIn("push:\n    branches:\n      - main", ci)
        self.assertIn("pull_request:\n    branches:\n      - main", ci)
        self.assertIn("runs-on: windows-latest", ci)
        self.assertIn("runs-on: macos-15", ci)
        self.assertIn("python -m unittest discover", ci)
        self.assertEqual(ci.count("node tests/run_extension_tests.js\n"), 2)
        self.assertEqual(ci.count("node tests/run_extension_tests.js --syntax"), 2)
        self.assertIn("uname -m", ci)
        self.assertIn("platform.machine()", ci)
        self.assertNotIn("PyInstaller", ci)
        self.assertNotIn("packaging/build_release.ps1", ci)
        self.assertNotIn("packaging/build_macos.sh", ci)
        self.assertNotIn("codesign", ci)
        self.assertNotIn("hdiutil", ci)

        self.assertIn("workflow_dispatch:", build)
        self.assertIn('runs-on: macos-15', build)
        self.assertIn('runs-on: macos-15-intel', build)
        self.assertIn('refs/tags/v', build)
        self.assertNotIn("branches:\n      - main", build)
        self.assertIn('if: startsWith(github.ref', build)
        self.assertIn('./packaging/build_release.ps1', build)
        self.assertIn('bash packaging/build_macos.sh', build)
        self.assertIn('bash packaging/build_macos.sh x86_64', build)
        self.assertNotIn("python -m unittest discover", build)
        self.assertNotIn("node tests/run_extension_tests.js", build)
        self.assertEqual(build.count('retention-days: 30'), 3)
        self.assertEqual(build.count('GITHUB_STEP_SUMMARY'), 3)

        runner = (ROOT / "tests" / "run_extension_tests.js").read_text(encoding="utf-8")
        self.assertIn(r"/^test_.*\.(js|mjs)$/", runner)

    def test_generated_mac_artifacts_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("assets/KOLConnect.icns", ignore)
        self.assertIn("packaging/.pyinstaller-build-macos/", ignore)
        self.assertIn("packaging/.pyinstaller-dist-macos/", ignore)

    def test_macos_intel_packaging_is_architecture_specific(self):
        build = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        script = (ROOT / "packaging" / "build_macos.sh").read_text(encoding="utf-8")

        self.assertIn("build-macos-arm64:", build)
        self.assertIn("build-macos-intel:", build)
        arm_job = build.split("  build-macos-arm64:", 1)[1].split("  build-macos-intel:", 1)[0]
        intel_job = build.split("  build-macos-intel:", 1)[1].split("  release:", 1)[0]
        self.assertNotIn("\n    needs:", arm_job)
        self.assertNotIn("\n    needs:", intel_job)
        self.assertIn("packaging/requirements-build.txt", intel_job)
        self.assertIn('[[ "$(uname -m)" == "x86_64" ]]', build)
        self.assertIn("KOLConnect-macos-arm64", build)
        self.assertIn("KOLConnect-macos-intel", build)
        self.assertIn("KOLConnect_v0.2.0_mac_arm64.dmg", build)
        self.assertIn("KOLConnect_v0.2.0_mac_intel.dmg", build)
        self.assertIn("- build-macos-intel", build)
        self.assertIn("actions/download-artifact@v4", build)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/v')", build)
        self.assertNotIn("branches:\n      - main", build)

        self.assertIn('TARGET_ARCH="${1:-arm64}"', script)
        self.assertIn("arm64)", script)
        self.assertIn("x86_64)", script)
        self.assertIn("KOLConnect_${VERSION}_mac_arm64.dmg", script)
        self.assertIn("KOLConnect_${VERSION}_mac_intel.dmg", script)
        self.assertIn('WORK_DIR="${PROJECT_ROOT}/build/pyinstaller-macos-intel"', script)
        self.assertIn("export MACOSX_DEPLOYMENT_TARGET=12.0", script)
        self.assertLess(
            script.index("export MACOSX_DEPLOYMENT_TARGET=12.0"),
            script.index("python -m PyInstaller"),
        )
        self.assertIn('lipo -archs "${APP_BINARY}"', script)
        self.assertIn('if [[ "${BINARY_ARCHES}" != "${TARGET_ARCH}" ]]', script)
        self.assertIn("Architecture mismatch", script)


if __name__ == "__main__":
    unittest.main()
