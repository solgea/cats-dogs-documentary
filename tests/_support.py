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
    packages_dir = destination / "content" / "packages"
    shutil.copytree(ROOT / "content" / "packages", packages_dir)
    shutil.copytree(ROOT / "content" / "batches", destination / "content" / "batches")
    for report in (destination / "content" / "batches").rglob("render-report.json"):
        report.unlink()

    # Bir istek render_path bildiriyorsa dosya da kopyalanmalı; aksi hâlde QA
    # doğrulaması (haklı olarak) kayıp çıktı raporlar. Yalnızca referans verilen
    # çıktılar kopyalanır, renders/ klasörünün tamamı değil.
    for request_file in packages_dir.rglob("viewmade-request.json"):
        try:
            request = load_json(request_file)
        except (OSError, ValueError):
            continue
        declared = str(request.get("render_path") or "").strip()
        if not declared:
            continue
        source = Path(declared)
        if not source.is_absolute():
            source = ROOT / declared
        target = destination / declared
        if source.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    (destination / "state").mkdir(parents=True, exist_ok=True)
    return Project(root=destination, state_dir=(destination / "state").resolve())
