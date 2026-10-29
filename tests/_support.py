"""Shared paths and temporary-project helpers for the test suite."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cddocs.config import Project  # noqa: E402  (path setup must run first)

BATCH_ID = "2026-10-29-cats-dogs-01"


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def copy_project(tmp_path: str | Path) -> Project:
    """Create an isolated writable project from the checked-in fixtures."""
    destination = Path(tmp_path).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "config", destination / "config")
    shutil.copytree(ROOT / "content" / "packages", destination / "content" / "packages")
    shutil.copytree(ROOT / "content" / "batches", destination / "content" / "batches")
    for report in (destination / "content" / "batches").rglob("render-report.json"):
        report.unlink()
    (destination / "state").mkdir(parents=True, exist_ok=True)
    return Project(root=destination, state_dir=(destination / "state").resolve())
