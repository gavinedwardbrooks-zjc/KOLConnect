from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from test_support.runtime_sandbox import (  # noqa: E402
    SANDBOX_ROOT,
    forbidden_root_test_artifacts,
    test_artifact_path,
)


class TestArtifactHygieneTests(unittest.TestCase):
    def test_no_legacy_test_artifacts_exist_at_repository_root(self) -> None:
        self.assertEqual([], forbidden_root_test_artifacts())

    def test_test_artifact_helper_stays_under_the_single_sandbox_root(self) -> None:
        path = test_artifact_path("hygiene", "case")
        self.assertTrue(path.is_relative_to(SANDBOX_ROOT.resolve()))

    def test_tests_do_not_explicitly_allocate_legacy_root_artifacts(self) -> None:
        forbidden = re.compile(
            r'(?:TemporaryDirectory\(dir=ROOT|ROOT\s*/\s*["\']\.(?:d4_|m[34567]_|pre_m8_))'
        )
        offenders = []
        for path in (ROOT / "tests").glob("test_*.py"):
            if path.name == Path(__file__).name:
                continue
            if forbidden.search(path.read_text(encoding="utf-8-sig")):
                offenders.append(path.name)
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
