#!/usr/bin/env python3
"""Verify January Method M serving artifacts are included in the backend image context.

Does not build or deploy. Checks Dockerfile.backend COPY + .dockerignore.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "artifacts/method_m_experimental_january/manifest.json",
    "artifacts/method_m_experimental_january/serving_hours.json",
    "artifacts/method_m_experimental_january/serving_notifications.json",
    "artifacts/method_m_experimental_january/INTEGRATION_VERIFY.md",
]


def main() -> int:
    dockerfile = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    if "COPY artifacts /app/artifacts" not in dockerfile:
        print("FAIL: Dockerfile.backend missing COPY artifacts /app/artifacts")
        return 1

    ignored = []
    for rel in REQUIRED:
        path = ROOT / rel
        if not path.is_file():
            print(f"FAIL: missing {rel}")
            return 1
        proc = subprocess.run(
            ["git", "check-ignore", "-v", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        # exit 0 => ignored; exit 1 => not ignored
        if proc.returncode == 0:
            ignored.append((rel, proc.stdout.strip()))

    if ignored:
        print("FAIL: required Method M artifacts are dockerignored:")
        for rel, why in ignored:
            print(f"  {rel}: {why}")
        return 1

    print("OK: Dockerfile copies artifacts/; Method M January files not dockerignored")
    for rel in REQUIRED:
        print(f"  include {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
