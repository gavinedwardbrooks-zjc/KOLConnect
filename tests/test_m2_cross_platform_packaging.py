from __future__ import annotations

import ast
import importlib.metadata
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
TESTS_DIR = ROOT / "tests"
MACOS_PYTHON_SHARD_PATTERNS = {
    "runtime-http": (
        "test_m2_*.py", "test_m4_*.py", "test_m5_*.py", "test_phase3_*.py",
        "test_agency_delete_sqlite.py", "test_campaign_execution_foundation.py",
        "test_dashboard_v2.py", "test_discovery_ux_consolidation.py",
        "test_discovery_workflow_polish.py", "test_fx_service.py", "test_locale_state_authority.py",
    ),
    "platform-integrations": (
        "test_m3_*.py", "test_m6_*.py", "test_m7_*.py", "test_m8_*.py", "test_plugin_*.py",
        "test_pre_m9_google_auth_status.py", "test_pre_m9_google_sheets_data_sync.py",
    ),
    "storage-foundation": (
        "test_pre_m8_*.py", "test_data_foundation_phase1.py",
        "test_data_foundation_phase1_6.py", "test_m1_b1_c1.py", "test_m1_c2_bio_archived_columns.py",
    ),
    "mail-followup-core": (
        "test_mail_followup_gate2.py", "test_mail_followup_gate3.py",
        "test_mail_followup_gate4.py", "test_mail_followup_gate5.py",
    ),
    "mail-security-core": (
        "test_mail_followup_google_sheets_replica.py", "test_mail_followup_ui_api.py",
        "test_targeted_gate_b_observability.py", "test_targeted_gate_c_mail_secret_storage.py",
        "test_targeted_gate_c1_mail_sync_redaction.py",
    ),
    "macos-keychain-canonical": (
        "test_targeted_gate_d_macos_keychain.py",
    ),
    "product-contracts": (
        "test_phase4_*.py", "test_pre_cloud_product_cleanup.py", "test_pre_m9_browser_mode_retirement.py",
        "test_pre_m9_email_deduplication.py", "test_release_critical_fixes.py",
        "test_test_artifact_hygiene.py", "test_uuid7_compatibility.py", "test_v2_*.py",
        "test_version_consistency.py",
    ),
}


def parse_macos_deployment_target(otool_output: str) -> str | None:
    """Mirror the workflow parser against deterministic ``otool -l`` fixtures."""
    command = ""
    for line in otool_output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "cmd":
            command = parts[1]
        elif len(parts) >= 2 and command == "LC_BUILD_VERSION" and parts[0] == "minos":
            return parts[1]
        elif len(parts) >= 2 and command == "LC_VERSION_MIN_MACOSX" and parts[0] == "version":
            return parts[1]
    return None


def is_macos_target_compatible(deployment_target: str, ceiling: int) -> bool:
    """Use an exact numeric deployment-target ceiling, not string comparison."""
    parts = deployment_target.split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return False
    major, minor, patch = (int(part) for part in (parts + ["0", "0"])[:3])
    return major < ceiling or (major == ceiling and minor == 0 and patch == 0)


def macos_unpatterned_python_runners(workflow: dict) -> list[str]:
    """Return macOS runner commands that would bypass shard ownership."""
    violations: list[str] = []
    for job_name, job in workflow.get("jobs", {}).items():
        if not str(job.get("runs-on", "")).startswith("macos"):
            continue
        for step in job.get("steps", []):
            run = step.get("run")
            if not isinstance(run, str):
                continue
            normalized_run = re.sub(r"\\\s*\n", " ", run)
            for line in normalized_run.splitlines():
                for command in re.split(r"(?:&&|;|\|\|)", line):
                    command = command.strip()
                    if command.startswith("#") or "scripts/run_python_tests.py" not in command:
                        continue
                    if not re.search(r"(?:^|\s)--pattern(?:\s|=)", command):
                        violations.append(f"{job_name}: {command}")
    return violations


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
    def test_macos_specs_explicitly_collect_feishu_http_tls_dependencies(self):
        for relative in (
            "packaging/spec/KOLConnect_mac.spec",
            "packaging/spec/KOLConnect_mac_intel.spec",
        ):
            with self.subTest(spec=relative):
                spec = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('"requests", "certifi"', spec)
                self.assertIn("collect_all(package_name)", spec)

    def test_macos_deployment_target_parser_supports_build_version_and_legacy_commands(self):
        build_version = """
            Load command 9
                  cmd LC_BUILD_VERSION
              cmdsize 32
             platform MACOS
                 minos 14.0
                   sdk 15.4
        """
        legacy_version = """
            Load command 8
                  cmd LC_VERSION_MIN_MACOSX
              cmdsize 16
              version 10.13
                  sdk 15.4
        """

        self.assertEqual("14.0", parse_macos_deployment_target(build_version))
        # Current Intel app evidence: an SDK of 15.4 does not change its 10.13 floor.
        self.assertEqual("10.13", parse_macos_deployment_target(legacy_version))
        self.assertTrue(is_macos_target_compatible("10.13", 14))
        self.assertTrue(is_macos_target_compatible("14.0", 14))

    def test_macos_deployment_target_compatibility_uses_architecture_specific_numeric_ceilings(self):
        macos_15 = """
            Load command 9
                  cmd LC_BUILD_VERSION
             platform MACOS
                 minos 15.0
                   sdk 15.4
        """
        self.assertEqual("15.0", parse_macos_deployment_target(macos_15))
        self.assertFalse(is_macos_target_compatible("14.1", 14))
        self.assertFalse(is_macos_target_compatible("15.0", 14))
        self.assertTrue(is_macos_target_compatible("15.0", 15))
        self.assertFalse(is_macos_target_compatible("15.1", 15))

    def test_macos_deployment_target_parser_fails_when_no_supported_command_exists(self):
        unsupported = """
            Load command 9
                  cmd LC_LOAD_DYLIB
              cmdsize 48
                  name /usr/lib/libSystem.B.dylib
                   sdk 15.4
        """
        self.assertIsNone(parse_macos_deployment_target(unsupported))

    def test_pywebview_owns_darwin_pyobjc_dependencies(self):
        requirements = (ROOT / "packaging" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pywebview", requirements.lower())
        self.assertIn("pyyaml>=6,<7", requirements.lower())
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
        self.assertIn("exclude_binaries=True", windows_spec)
        self.assertIn("COLLECT(", windows_spec)
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
        manual_path = workflow_dir / "build-macos-client.yml"
        self.assertTrue(manual_path.is_file())
        manual = manual_path.read_text(encoding="utf-8")

        self.assertIn("arm64_test_only:", manual)
        self.assertIn("source_sha:", manual)
        self.assertIn("fromJSON(inputs.arm64_test_only", manual)
        self.assertIn("KOLConnect_v2.0.0_macOS_arm64_TEST.dmg", manual)
        self.assertIn("inputs.source_sha || github.sha", manual)
        self.assertIn("pyi-archive_viewer -r -b", manual)
        self.assertIn("FEISHU_FIELD_FETCH_FAILED", manual)
        self.assertIn("name: ${{ env.ARTIFACT_NAME }}", manual)
        self.assertIn("path: frozen-src/${{ env.TARGET_DMG }}", manual)
        self.assertNotIn("softprops/action-gh-release", manual)

        self.assertIn("workflow_dispatch:", ci)
        self.assertIn("push:\n    branches:\n      - main", ci)
        self.assertIn("pull_request:\n    branches:\n      - main", ci)
        self.assertIn("runs-on: windows-latest", ci)
        self.assertIn("runs-on: macos-15", ci)
        self.assertEqual(ci.count("python scripts/run_python_tests.py --verbosity 1"), 1)
        workflow = yaml.safe_load(ci)
        self.assertFalse(macos_unpatterned_python_runners(workflow))
        unpatterned_macos = {
            "jobs": {
                "macos-validation": {
                    "runs-on": "macos-15",
                    "steps": [{
                        "run": "echo validation && PYTHONUNBUFFERED=1 python -u scripts/run_python_tests.py --verbosity 2",
                    }],
                },
            },
        }
        patterned_macos = {
            "jobs": {
                "macos-validation": {
                    "runs-on": "macos-15",
                    "steps": [{
                        "run": "python -u \\\n                            scripts/run_python_tests.py --pattern 'test_mail_*.py' --verbosity 2",
                    }],
                },
            },
        }
        unpatterned_windows = {
            "jobs": {
                "windows-validation": {
                    "runs-on": "windows-latest",
                    "steps": [{
                        "run": "python scripts/run_python_tests.py --verbosity 1",
                    }],
                },
            },
        }
        self.assertTrue(macos_unpatterned_python_runners(unpatterned_macos))
        self.assertFalse(macos_unpatterned_python_runners(patterned_macos))
        self.assertFalse(macos_unpatterned_python_runners(unpatterned_windows))
        jobs = workflow["jobs"]
        keychain_job = jobs["test-macos-arm64-keychain"]
        shard_job = jobs["test-macos-arm64-python"]
        static_job = jobs["test-macos-arm64-extension-static"]
        self.assertEqual("test-macos-arm64-keychain", shard_job["needs"])
        self.assertEqual(
            ["test-macos-arm64-keychain", "test-macos-arm64-python"],
            static_job["needs"],
        )
        self.assertFalse(shard_job["strategy"]["fail-fast"])
        matrix = shard_job["strategy"]["matrix"]["include"]
        self.assertEqual(7, len(matrix))
        self.assertEqual(
            {entry["shard"]: tuple(entry["patterns"].split(",")) for entry in matrix},
            MACOS_PYTHON_SHARD_PATTERNS,
        )
        self.assertNotIn("storage-mail-security", MACOS_PYTHON_SHARD_PATTERNS)
        self.assertEqual(
            (
                "test_pre_m8_*.py",
                "test_data_foundation_phase1.py",
                "test_data_foundation_phase1_6.py",
                "test_m1_b1_c1.py",
                "test_m1_c2_bio_archived_columns.py",
            ),
            MACOS_PYTHON_SHARD_PATTERNS["storage-foundation"],
        )
        self.assertEqual(
            (
                "test_mail_followup_gate2.py",
                "test_mail_followup_gate3.py",
                "test_mail_followup_gate4.py",
                "test_mail_followup_gate5.py",
            ),
            MACOS_PYTHON_SHARD_PATTERNS["mail-followup-core"],
        )
        self.assertEqual(
            (
                "test_mail_followup_google_sheets_replica.py",
                "test_mail_followup_ui_api.py",
                "test_targeted_gate_b_observability.py",
                "test_targeted_gate_c_mail_secret_storage.py",
                "test_targeted_gate_c1_mail_sync_redaction.py",
            ),
            MACOS_PYTHON_SHARD_PATTERNS["mail-security-core"],
        )
        self.assertEqual(
            ("test_targeted_gate_d_macos_keychain.py",),
            MACOS_PYTHON_SHARD_PATTERNS["macos-keychain-canonical"],
        )
        self.assertEqual(
            {entry["shard"]: entry["timeout_minutes"] for entry in matrix},
            {
                "runtime-http": 30,
                "platform-integrations": 30,
                "storage-foundation": 30,
                "mail-followup-core": 30,
                "mail-security-core": 30,
                "macos-keychain-canonical": 30,
                "product-contracts": 20,
            },
        )
        self.assertIn("name: Validate native macOS Keychain", ci)
        self.assertIn(
            "-m unittest discover -s tests -p 'test_targeted_gate_d_macos_keychain.py' -k native_keychain_round_trip_update_and_delete -v",
            ci,
        )
        self.assertEqual("macos-15", keychain_job["runs-on"])
        self.assertIn("timeout-minutes: 3", ci)
        self.assertNotIn("continue-on-error:", ci)
        self.assertNotIn("name: Run Python tests\n        id: python_tests", ci.split("  test-macos-arm64-keychain:", 1)[1])
        self.assertIn("PYTHONUNBUFFERED=1 python -u scripts/run_python_tests.py --pattern", ci)
        self.assertIn("mail-security-core|macos-keychain-canonical", ci)
        self.assertIn("MODULE_TIMING ${pattern}", ci)
        self.assertIn('if [ "${status}" -ne 0 ]; then', ci)
        self.assertIn("node tests/run_extension_tests.js", ci)
        self.assertNotIn("python -m unittest discover", ci)
        self.assertEqual(ci.count('HOMEBREW_NO_AUTO_UPDATE: "1"'), 2)
        self.assertNotIn("brew update", ci)
        self.assertEqual(ci.count("brew install sqlite"), 2)
        self.assertEqual(ci.count("brew upgrade sqlite"), 2)
        self.assertEqual(ci.count("brew install python@3.12"), 2)
        self.assertEqual(ci.count('python_prefix="$(brew --prefix python@3.12)"'), 2)
        self.assertEqual(ci.count('python_bin="${python_prefix}/bin/python3.12"'), 2)
        self.assertEqual(ci.count('test -x "${python_bin}"'), 2)
        self.assertEqual(ci.count('sys.version_info[:2] == (3, 12)'), 2)
        self.assertEqual(ci.count('"${python_bin}" -m venv .venv-ci'), 2)
        self.assertEqual(ci.count("The formula built, but is not symlinked"), 2)
        self.assertEqual(ci.count("Could not symlink"), 2)
        self.assertNotIn("brew upgrade python@3.12", ci)
        self.assertNotIn("brew unlink openssl@1.1", ci)
        self.assertNotIn("brew link --overwrite openssl@3", ci)
        self.assertNotIn("|| true", ci)
        self.assertIn("python scripts/check_sqlite_runtime.py", ci)
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
        self.assertEqual(build.count('HOMEBREW_NO_AUTO_UPDATE: "1"'), 2)
        self.assertEqual(build.count("brew install sqlite"), 2)
        self.assertEqual(build.count("brew upgrade sqlite"), 2)
        self.assertEqual(build.count("brew install python@3.12"), 2)
        self.assertEqual(build.count('python_prefix="$(brew --prefix python@3.12)"'), 2)
        self.assertEqual(build.count('python_bin="${python_prefix}/bin/python3.12"'), 2)
        self.assertEqual(build.count('"${python_bin}" -m venv .venv-ci'), 2)
        self.assertEqual(
            build.count("The formula built, but is not symlinked"), 2
        )
        self.assertEqual(build.count("Could not symlink"), 2)
        self.assertNotIn("brew link --overwrite", build)
        self.assertEqual(build.count("python scripts/check_sqlite_runtime.py"), 2)
        self.assertNotIn("python -m unittest discover", build)
        self.assertNotIn("node tests/run_extension_tests.js", build)
        self.assertEqual(build.count('retention-days: 30'), 3)
        self.assertEqual(build.count('GITHUB_STEP_SUMMARY'), 3)

        self.assertIn("name: Build macOS Clients", manual)
        self.assertRegex(manual, r"(?m)^on:\n  workflow_dispatch:\s*$")
        for forbidden_trigger in ("push", "pull_request", "schedule", "workflow_run"):
            self.assertNotRegex(manual, rf"(?m)^  {forbidden_trigger}:")
        manual_workflow = yaml.safe_load(manual)
        self.assertEqual(["build-macos-client"], list(manual_workflow["jobs"]))
        self.assertEqual({"contents": "read"}, manual_workflow["permissions"])
        manual_job = manual_workflow["jobs"]["build-macos-client"]
        self.assertEqual("${{ matrix.runner }}", manual_job["runs-on"])
        self.assertNotIn("needs", manual_job)
        self.assertEqual("1", manual_job["env"]["HOMEBREW_NO_AUTO_UPDATE"])

        frozen_sha = "4b2833bd9d6c797d459cba72bf4a9949d1d1d9d2"
        workflow_env = manual_workflow["env"]
        self.assertEqual(frozen_sha, workflow_env["FROZEN_RELEASE_SHA"])
        self.assertEqual("2.0.0", workflow_env["PRODUCT_VERSION"])
        self.assertEqual("frozen-src", workflow_env["FROZEN_PRODUCT_ROOT"])
        matrix_expression = manual_job["strategy"]["matrix"]["include"]
        self.assertFalse(manual_job["strategy"]["fail-fast"])
        matrix_match = re.fullmatch(
            r"\$\{\{ fromJSON\(inputs\.arm64_test_only && '(.+)' \|\| '(.+)'\) \}\}",
            matrix_expression,
        )
        self.assertIsNotNone(matrix_match)
        arm_only_matrix = json.loads(matrix_match.group(1))
        dual_arch_matrix = json.loads(matrix_match.group(2))
        expected_matrix = {
            "arm64": {
                "arch": "arm64",
                "runner": "macos-14",
                "target_min_macos": "14",
                "build_argument": "",
                "source_dmg": "release/KOLConnect_v2.0.0_mac_arm64.dmg",
                "target_dmg": "release/KOLConnect_v2.0.0_macOS_arm64.dmg",
                "artifact_name": "KOLConnect-v2.0.0-macOS-arm64",
                "app_path": "packaging/.pyinstaller-dist-macos/KOLConnect.app",
            },
            "x86_64": {
                "arch": "x86_64",
                "runner": "macos-15-intel",
                "target_min_macos": "14",
                "build_argument": "x86_64",
                "source_dmg": "release/KOLConnect_v2.0.0_mac_intel.dmg",
                "target_dmg": "release/KOLConnect_v2.0.0_macOS_x64.dmg",
                "artifact_name": "KOLConnect-v2.0.0-macOS-x64",
                "app_path": "dist/pyinstaller-macos-intel/KOLConnect.app",
            },
        }
        self.assertEqual(
            [expected_matrix["arm64"]],
            arm_only_matrix,
        )
        self.assertEqual(
            expected_matrix,
            {entry["arch"]: entry for entry in dual_arch_matrix},
        )

        checkout_steps = [
            step for step in manual_job["steps"] if step.get("uses") == "actions/checkout@v4"
        ]
        self.assertEqual(2, len(checkout_steps))
        root_checkout, frozen_checkout = checkout_steps
        self.assertEqual(
            "${{ inputs.arm64_test_only && (inputs.source_sha || github.sha) || 'main' }}",
            root_checkout["with"]["ref"],
        )
        self.assertNotIn("path", root_checkout["with"])
        self.assertEqual(
            "${{ inputs.arm64_test_only && (inputs.source_sha || github.sha) || '"
            + frozen_sha
            + "' }}",
            frozen_checkout["with"]["ref"],
        )
        self.assertEqual("frozen-src", frozen_checkout["with"]["path"])
        self.assertEqual(1, frozen_checkout["with"]["fetch-depth"])

        steps_by_name = {
            step["name"]: step
            for step in manual_job["steps"]
            if "name" in step
        }
        revision_check = steps_by_name["Enforce selected source revision"]["run"]
        self.assertIn('git -C "${FROZEN_PRODUCT_ROOT}" rev-parse HEAD', revision_check)
        self.assertIn('"${actual_sha}" == "${EXPECTED_SOURCE_SHA}"', revision_check)
        self.assertIn("exit 1", revision_check)

        self.assertIn("Build job-local SQLite 3.51.3 and Python 3.12", manual)
        self.assertIn("sqlite-autoconf-3510300.tar.gz", manual)
        self.assertIn("https://www.sqlite.org/2026/sqlite-autoconf-3510300.tar.gz", manual)
        self.assertNotIn("https://www.sqlite.org/2025/sqlite-autoconf-3510300.tar.gz", manual)
        self.assertIn("Python-${PYTHON_SOURCE_VERSION}.tgz", manual)
        self.assertIn('MACOSX_DEPLOYMENT_TARGET: "14.0"', manual)
        self.assertIn('python3 "${FROZEN_PRODUCT_ROOT}/scripts/check_sqlite_runtime.py"', manual)
        self.assertIn("CUSTOM_PYTHON_PREFIX", manual)
        self.assertIn('ln -sf python3 "${python_prefix}/bin/python"', manual)
        self.assertIn('[[ "$(command -v python)" == "${CUSTOM_PYTHON_PREFIX}/bin/python" ]]', manual)
        self.assertIn("--enable-shared", manual)
        self.assertIn('libpython3.12.dylib', manual)
        self.assertIn('shared_minos=', manual)
        self.assertNotRegex(
            manual,
            r"brew\s+(?:unlink|link(?:\s+--overwrite)?)\s+openssl(?:@\S+)?",
        )
        self.assertIn('[[ "$(uname -m)" == "${TARGET_ARCH}" ]]', manual)
        self.assertIn("platform.machine()", manual)
        self.assertIn('python3 "${FROZEN_PRODUCT_ROOT}/scripts/check_sqlite_runtime.py"', manual)

        version_check = steps_by_name["Assert v2.0.0 version metadata"]["run"]
        self.assertIn("from app.version import APP_VERSION", version_check)
        self.assertIn('expected = "2.0.0"', version_check)
        self.assertIn("CFBundleShortVersionString", version_check)
        self.assertIn("CFBundleVersion", version_check)

        release_tests = steps_by_name["Run macOS release contract tests"]["run"]
        for pattern in (
            "test_m2_cross_platform_packaging.py",
            "test_version_consistency.py",
            "test_targeted_gate_d_macos_keychain.py",
        ):
            self.assertIn(f"--pattern {pattern}", release_tests)

        self.assertIn("bash packaging/build_macos.sh", manual)
        build_step = steps_by_name["Build native macOS client"]
        self.assertEqual("frozen-src", build_step["working-directory"])
        self.assertEqual(
            "frozen-src",
            steps_by_name["Install packaging dependencies"]["working-directory"],
        )
        packaging_install = steps_by_name["Install packaging dependencies"]["run"]
        self.assertIn("PYINSTALLER_COMPILE_BOOTLOADER=1", packaging_install)
        self.assertIn("--no-binary=PyInstaller", packaging_install)
        self.assertIn('bootloader_minos=', packaging_install)
        self.assertIn(
            '"${bootloader_minos}" == "${MACOSX_DEPLOYMENT_TARGET}"',
            packaging_install,
        )
        self.assertEqual(
            "frozen-src",
            steps_by_name["Assert v2.0.0 version metadata"]["working-directory"],
        )
        self.assertEqual("${{ matrix.target_min_macos }}", manual_job["env"]["TARGET_MIN_MACOS"])
        verification = steps_by_name["Verify macOS deployment targets and packaged resources"]["run"]
        for contract in (
            'file "${target}"',
            'lipo -info "${target}"',
            'lipo -archs "${target}"',
            'otool -l "$1"',
            "extract_macos_minimum",
            "LC_BUILD_VERSION",
            "LC_VERSION_MIN_MACOSX",
            "is_macos_target_compatible",
            "PYEXPAT",
            "pyexpat.cpython-312-darwin.so",
            "TARGET_MIN_MACOS",
            '"${minos}" == "${MACOSX_DEPLOYMENT_TARGET}"',
            "FROZEN_PRODUCT_ROOT",
            "CFBundleShortVersionString",
            "CFBundleVersion",
            "webapp/index.html",
            "chrome_extension/manifest.json",
            "chrome_extension/tests",
            "chrome_extension/README.md",
            '"${binary}" --sqlite-runtime-check',
            "codesign --force --deep --sign -",
            "codesign --verify --deep --strict",
            'pyi-archive_viewer -r -b "${binary}"',
            'cmp -s "${source_settings}" "${packaged_settings}"',
            'cmp -s "${source_i18n}" "${packaged_i18n}"',
            "PACKAGED_SETTINGS_PATH=",
            "PACKAGED_I18N_PATH=",
            "SETTINGS_MARKER_FOUND=YES",
            "I18N_MARKER_FOUND=YES",
            "certifi/cacert.pem",
        ):
            self.assertIn(contract, verification)
        self.assertNotIn('pyi-archive_viewer -l "${binary}"', verification)
        for failed_gate in (
            "sqlite_runtime_relocatability",
            "bundle_short_version",
            "bundle_version",
            "packaged_webapp_index",
            "packaged_webapp_app_js",
            "packaged_webapp_styles",
            "packaged_webapp_i18n",
            "packaged_settings_file",
            "packaged_i18n_file",
            "packaged_settings_source_mismatch",
            "packaged_i18n_source_mismatch",
            "packaged_settings_feishu_error",
            "packaged_i18n_feishu_error",
            "source_feishu_client_marker",
            "source_feishu_service_marker",
            "macos_tls_ca_spec",
            "pyinstaller_archive_open",
            "packaged_feishu_client_module",
            "packaged_feishu_sync_service_module",
            "packaged_requests_module",
            "packaged_certifi_module",
            "packaged_certifi_ca_bundle",
            "packaged_app_icon",
            "packaged_extension_manifest",
            "packaged_extension_tests_removed",
            "packaged_extension_readme_removed",
            "packaged_sqlite_runtime",
            "codesign_apply",
            "codesign_verify",
        ):
            self.assertIn(f"fail_gate {failed_gate}", verification)

        smoke = steps_by_name["Smoke test packaged imports and app with isolated HOME"]["run"]
        for contract in (
            'HOME="${smoke_home}"',
            'TMPDIR="${smoke_tmp}"',
            '"${binary}"',
            "http://127.0.0.1:8765/",
            "pages/dashboard.js",
            "Library/Application Support/KOLConnect",
            "kolconnect.db",
            "PACKAGED_EXPAT_SMOKE=PASS",
            "PACKAGED_ELEMENTTREE_SMOKE=PASS",
            "PACKAGED_OPENPYXL_SMOKE=PASS",
            "PACKAGED_APP_LAUNCH=PASS",
        ):
            self.assertIn(contract, smoke)

        dmg_build = steps_by_name["Create final macOS DMG"]["run"]
        self.assertIn("hdiutil create", dmg_build)
        self.assertIn('product_dmg="${FROZEN_PRODUCT_ROOT}/${TARGET_DMG}"', dmg_build)
        self.assertIn("KOLConnect_v2.0.0_macOS_arm64_TEST.dmg", dmg_build)
        self.assertIn("fail_gate dmg_output_filename", dmg_build)
        self.assertIn("fail_gate dmg_create", dmg_build)
        dmg_validation = steps_by_name["Validate DMG and calculate SHA-256"]["run"]
        self.assertIn("hdiutil attach -readonly -nobrowse", dmg_validation)
        self.assertIn('test -d "${mount_dir}/KOLConnect.app"', dmg_validation)
        self.assertIn("shasum -a 256", dmg_validation)
        self.assertIn("ARTIFACT_SIZE_BYTES=", dmg_validation)
        self.assertIn("ARTIFACT_SHA256=", dmg_validation)
        self.assertIn("DMG_VALIDATION=PASS", dmg_validation)
        for failed_gate in (
            "dmg_nonempty",
            "dmg_freshness",
            "dmg_mount",
            "dmg_app_present",
            "dmg_applications_link",
            "dmg_app_architecture",
            "dmg_app_version",
            "dmg_app_codesign",
            "dmg_detach",
            "dmg_size",
        ):
            self.assertIn(f"fail_gate {failed_gate}", dmg_validation)

        summary = steps_by_name["Write build summary"]["run"]
        for metadata in (
            "${ACTUAL_BUILD_SHA}",
            "${{ matrix.runner }}",
            "${TARGET_ARCH}",
            "${PYTHON_VERSION}",
            "${TARGET_DMG}",
            "${ARTIFACT_NAME}",
            "${ARTIFACT_SHA256}",
            "ad-hoc",
            "notarization: none",
            "Gatekeeper",
        ):
            self.assertIn(metadata, summary)

        upload_step = next(
            step for step in manual_job["steps"] if step.get("uses") == "actions/upload-artifact@v4"
        )
        self.assertEqual("${{ env.ARTIFACT_NAME }}", upload_step["with"]["name"])
        self.assertEqual("frozen-src/${{ env.TARGET_DMG }}", upload_step["with"]["path"])
        self.assertEqual("error", upload_step["with"]["if-no-files-found"])
        self.assertEqual(30, upload_step["with"]["retention-days"])

        self.assertNotIn("softprops/action-gh-release", manual)
        self.assertNotIn("contents: write", manual)
        self.assertNotIn("continue-on-error", manual)
        self.assertNotIn("set +e", manual)
        self.assertNotIn("Developer ID", manual)
        self.assertNotIn("secrets.", manual)

        runner = (ROOT / "tests" / "run_extension_tests.js").read_text(encoding="utf-8")
        self.assertIn(r"/^test_.*\.(js|mjs)$/", runner)

    def test_macos_python_shards_assign_every_canonical_test_module_once(self):
        canonical_modules = {path.name for path in TESTS_DIR.glob("test_*.py")}
        owners: dict[str, list[str]] = {}
        for shard, patterns in MACOS_PYTHON_SHARD_PATTERNS.items():
            matches = [
                path.name
                for pattern in patterns
                for path in TESTS_DIR.glob(pattern)
            ]
            matched = set(matches)
            self.assertTrue(matched, f"{shard} has no matching test modules")
            self.assertEqual(
                len(matches),
                len(matched),
                f"Overlapping patterns within {shard}: {patterns}",
            )
            for module in matched:
                owners.setdefault(module, []).append(shard)

        unassigned = canonical_modules - set(owners)
        duplicate_owners = {
            module: module_owners
            for module, module_owners in owners.items()
            if len(module_owners) != 1
        }
        self.assertFalse(unassigned, f"Unassigned macOS shard modules: {sorted(unassigned)}")
        self.assertFalse(duplicate_owners, f"Duplicate macOS shard modules: {duplicate_owners}")
        self.assertEqual(canonical_modules, set(owners))

    def test_generated_mac_artifacts_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("assets/KOLConnect.icns", ignore)
        self.assertIn("packaging/.pyinstaller-build-macos/", ignore)
        self.assertIn("packaging/.pyinstaller-dist-macos/", ignore)

    def test_windows_release_publication_cleans_only_named_staging_directories(self):
        script = (ROOT / "packaging" / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn('Get-ChildItem -LiteralPath $release -Directory -Filter ".staging-*"', script)
        self.assertIn("Canonical release artifacts remain untouched until this candidate validates.", script)
        self.assertLess(
            script.index('Get-ChildItem -LiteralPath $release -Directory -Filter ".staging-*"'),
            script.index("Copy-Item -LiteralPath $builtDirectory -Destination $stagingDirectory -Recurse"),
        )
        self.assertLess(
            script.index("Move-Item -LiteralPath $stagingDirectory -Destination $releaseDirectory"),
            script.index("Remove-Item -LiteralPath $stagingRoot -Force"),
        )

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
        self.assertIn("KOLConnect_v2.0.0_mac_arm64.dmg", build)
        self.assertIn("KOLConnect_v2.0.0_mac_intel.dmg", build)
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
        self.assertIn(
            'export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-14.0}"',
            script,
        )
        self.assertIn(
            'if [[ "${MACOSX_DEPLOYMENT_TARGET}" != "14.0" ]]',
            script,
        )
        self.assertNotIn("MACOSX_DEPLOYMENT_TARGET=12.0", script)
        self.assertLess(
            script.index('export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-14.0}"'),
            script.index("python -m PyInstaller"),
        )
        self.assertIn('lipo -archs "${APP_BINARY}"', script)
        self.assertIn('if [[ "${BINARY_ARCHES}" != "${TARGET_ARCH}" ]]', script)
        self.assertIn("Architecture mismatch", script)


if __name__ == "__main__":
    unittest.main()
