from __future__ import annotations

"""Run unittest discovery after installing the canonical test sandbox."""

import argparse
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))

from test_support.runtime_sandbox import (  # noqa: E402
    CLEANUP_WARNINGS,
    forbidden_root_test_artifacts,
    test_runtime_sandbox,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--verbosity", type=int, default=1)
    args = parser.parse_args()

    result = None
    try:
        with test_runtime_sandbox("full_python"):
            suite = unittest.defaultTestLoader.discover(
                str(TESTS), pattern=args.pattern, top_level_dir=str(TESTS)
            )
            result = unittest.TextTestRunner(verbosity=args.verbosity).run(suite)
    finally:
        leaked_artifacts = forbidden_root_test_artifacts()
    for warning in CLEANUP_WARNINGS:
        print(f"ENVIRONMENT_CLEANUP_WARNING: {warning}", file=sys.stderr)
    if leaked_artifacts:
        print(
            "TEST_ROOT_ARTIFACTS_DETECTED: "
            + ", ".join(str(path) for path in leaked_artifacts),
            file=sys.stderr,
        )
        return 1
    return 0 if result is not None and result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
