"""Project configuration, paths, and environment-only runtime settings."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .util import PipelineError, find_project_root, read_json

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _require_mapping(data: Any, label: str) -> dict:
    if not isinstance(data, dict):
        raise PipelineError(f"{label} must be a JSON object")
    return data


def _require_list(data: dict, key: str, label: str) -> list:
    value = data.get(key)
    if not isinstance(value, list):
        raise PipelineError(f"{label}.{key} must be a list")
    return value


def load_dotenv(path: str | Path) -> dict[str, str]:
    """Minimal .env reader. Existing process variables always win."""
    target = Path(path)
    loaded: dict[str, str] = {}
    if not target.is_file():
        return loaded
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(value[0]) and len(value) >= 2:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


@dataclass(frozen=True)
class Project:
    root: Path
    state_dir: Path

    @classmethod
    def open(cls, start: str | Path | None = None) -> "Project":
        root = find_project_root(start)
        state_override = os.environ.get("CDDOCS_STATE_DIR")
        state_dir = Path(state_override).expanduser() if state_override else root / "state"
        if not state_dir.is_absolute():
            state_dir = root / state_dir
        return cls(root=root, state_dir=state_dir.resolve())

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def content_dir(self) -> Path:
        return self.root / "content"

    @property
    def packages_dir(self) -> Path:
        return self.content_dir / "packages"

    @property
    def batches_dir(self) -> Path:
        return self.content_dir / "batches"

    @property
    def schemas_dir(self) -> Path:
        return self.root / "schemas"

    @property
    def renders_dir(self) -> Path:
        return self.root / "renders"

    @property
    def dist_dir(self) -> Path:
        return self.root / "dist"

    @property
    def history_db(self) -> Path:
        return self.state_dir / "history.db"

    @property
    def history_export(self) -> Path:
        return self.state_dir / "history.json"

    @property
    def viewmade_token_file(self) -> Path:
        return self.state_dir / "viewmade-token.json"

    @property
    def viewmade_client_file(self) -> Path:
        return self.state_dir / "viewmade-oauth-client.json"

    @property
    def viewmade_tools_file(self) -> Path:
        return self.state_dir / "viewmade-tools.json"

    @property
    def viewmade_binding_file(self) -> Path:
        return self.state_dir / "viewmade-binding.json"

    def channel(self) -> dict:
        data = _require_mapping(read_json(self.config_dir / "channel.json"), "channel.json")
        format_cfg = _require_mapping(data.get("format"), "channel.format")
        width = format_cfg.get("width")
        height = format_cfg.get("height")
        if format_cfg.get("aspect_ratio") != "9:16":
            raise PipelineError("channel.format.aspect_ratio must be 9:16")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise PipelineError("channel.format width/height must be positive integers")
        if width * 16 != height * 9:
            raise PipelineError("channel.format dimensions must preserve 9:16")
        low = format_cfg.get("min_duration_s")
        high = format_cfg.get("max_duration_s")
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or low >= high:
            raise PipelineError("channel.format duration bounds are invalid")
        editorial = _require_mapping(data.get("editorial"), "channel.editorial")
        visual = _require_mapping(data.get("visual"), "channel.visual")
        if not editorial.get("required_disclosure"):
            raise PipelineError("channel.editorial.required_disclosure is required")
        if not visual.get("negative_prompt"):
            raise PipelineError("channel.visual.negative_prompt is required")
        return data

    def sources(self) -> dict:
        data = _require_mapping(read_json(self.config_dir / "sources.json"), "sources.json")
        _require_list(data, "allowed_domains", "sources")
        _require_list(data, "banned_domains", "sources")
        return data

    def viewmade(self) -> dict:
        data = _require_mapping(read_json(self.config_dir / "viewmade.json"), "viewmade.json")
        for key in ("mcp_url", "authorization_metadata_url", "connect_url"):
            if not isinstance(data.get(key), str) or not data[key].startswith("https://"):
                raise PipelineError(f"viewmade.{key} must be an https URL")
        scopes = _require_list(data, "scopes", "viewmade")
        if not scopes:
            raise PipelineError("viewmade.scopes must not be empty")
        return data

    def batch_path(self, batch_id: str) -> Path:
        if not _ID_RE.fullmatch(batch_id):
            raise PipelineError(f"invalid batch id: {batch_id!r}")
        return self.batches_dir / batch_id

    def package_path(self, slug: str) -> Path:
        if not _ID_RE.fullmatch(slug):
            raise PipelineError(f"invalid package slug: {slug!r}")
        return self.packages_dir / slug

    def load_package(self, slug: str) -> tuple[dict, dict, Path]:
        folder = self.package_path(slug)
        package = _require_mapping(read_json(folder / "package.json"), f"{slug}/package.json")
        research = _require_mapping(read_json(folder / "research.json"), f"{slug}/research.json")
        if package.get("id") != slug:
            raise PipelineError(f"{slug}/package.json id {package.get('id')!r} does not match folder")
        if research.get("package_id") != slug:
            raise PipelineError(
                f"{slug}/research.json package_id {research.get('package_id')!r} does not match folder"
            )
        return package, research, folder

    def load_batch(self, batch_id: str) -> tuple[dict, Path]:
        folder = self.batch_path(batch_id)
        batch = _require_mapping(read_json(folder / "batch.json"), f"{batch_id}/batch.json")
        if batch.get("batch_id") != batch_id:
            raise PipelineError(
                f"{batch_id}/batch.json batch_id {batch.get('batch_id')!r} does not match folder"
            )
        packages = _require_list(batch, "packages", "batch")
        if not packages:
            raise PipelineError(f"batch {batch_id} lists no packages")
        if len(set(packages)) != len(packages):
            raise PipelineError(f"batch {batch_id} contains duplicate package ids")
        for slug in packages:
            if not isinstance(slug, str) or not _ID_RE.fullmatch(slug):
                raise PipelineError(f"batch {batch_id} has invalid package id: {slug!r}")
        return batch, folder

    def package_folders(self) -> list[Path]:
        if not self.packages_dir.is_dir():
            return []
        return sorted(
            (path for path in self.packages_dir.iterdir() if (path / "package.json").is_file()),
            key=lambda path: path.name,
        )

    def batch_folders(self) -> list[Path]:
        if not self.batches_dir.is_dir():
            return []
        return sorted(
            (path for path in self.batches_dir.iterdir() if (path / "batch.json").is_file()),
            key=lambda path: path.name,
        )


@dataclass(frozen=True)
class Settings:
    mcp_token: str | None = None
    live_confirm: str = ""
    state_dir: Path | None = None
    environ: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def from_env(cls, project: Project) -> "Settings":
        load_dotenv(project.root / ".env")
        return cls(
            mcp_token=os.environ.get("VIEWMADE_MCP_TOKEN") or None,
            live_confirm=os.environ.get("CDDOCS_LIVE_CONFIRM", ""),
            state_dir=project.state_dir,
            environ=dict(os.environ),
        )

    def live_authorised(self, cli_allow_live: bool) -> bool:
        return bool(cli_allow_live) and self.live_confirm.strip().upper() == "YES"

    def require_live_authorisation(self, cli_allow_live: bool, *, provider: str) -> None:
        if not cli_allow_live:
            raise PipelineError(
                f"Live {provider} rendering is disabled. Re-run with --allow-live and set "
                f"{os.environ.get('CDDOCS_LIVE_CONFIRM_ENV', 'CDDOCS_LIVE_CONFIRM')}=YES."
            )
        if self.live_confirm.strip().upper() != "YES":
            raise PipelineError(
                "Live rendering needs explicit environment confirmation: set CDDOCS_LIVE_CONFIRM=YES."
            )
