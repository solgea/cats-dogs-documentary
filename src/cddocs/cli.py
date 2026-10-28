"""Command-line interface for the cats-and-dogs documentary pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .batch import (
    build_batch,
    build_package,
    package_batch,
    render_batch,
    validate_batch,
    validate_package_folder,
)
from .config import Project, Settings
from .history import History
from .viewmade.adapter import ViewMadeAdapter, ViewMadeBlocked
from .viewmade.oauth import OAuthError
from .viewmade.mcp import MCPError


DEFAULT_TEMPLATES = {
    "render": {
        "prompt": "$prompt",
        "duration": "$duration_s",
        "aspect_ratio": "$aspect_ratio",
    },
    "status": {"job_id": "$job_id"},
    "download": {"job_id": "$job_id"},
}


def _json_print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _open_project(args: argparse.Namespace) -> Project:
    return Project.open(args.root)


def _print_result(result, *, as_json: bool) -> None:
    if as_json:
        _json_print(result.to_dict(artifacts=result.artifacts))
        return
    print(f"{result.package_id}: {result.status} ({result.package_id})")
    counts = result.counts
    print(
        f"  checks: {counts['PASS']} pass, {counts['WARN']} warn, "
        f"{counts['FAIL']} fail, {counts['SKIP']} skip"
    )
    print(f"  render: {result.render_status}; publish_ready: {str(result.publish_ready).lower()}")
    for check in result.checks:
        if check.status in {"FAIL", "WARN"}:
            print(f"  [{check.status}] {check.id}: {check.detail}")


def _print_outcome(outcome, *, as_json: bool) -> None:
    if as_json:
        _json_print(outcome.to_dict())
        return
    print(f"Batch {outcome.batch_id}: {outcome.status}")
    for result in outcome.results:
        counts = result.counts
        print(
            f"  {result.package_id:<28} {result.status:<5} "
            f"(pass {counts['PASS']}, warn {counts['WARN']}, fail {counts['FAIL']})"
        )
    if outcome.pairs:
        print("  duplicate pairs:")
        for pair in outcome.pairs:
            print(
                f"    {pair['left']} <-> {pair['right']}: "
                f"{pair['similarity']:.3f} {pair['severity']}"
            )
    print(f"  report: {outcome.report_path}")
    if outcome.history_path:
        print(f"  history: {outcome.history_path}")
    fails = [check for result in outcome.results for check in result.checks if check.status == "FAIL"]
    warns = [check for result in outcome.results for check in result.checks if check.status == "WARN"]
    for check in fails:
        print(f"  [FAIL] {check.id}: {check.detail}")
    for check in warns:
        print(f"  [WARN] {check.id}: {check.detail}")


def cmd_batch_build(args: argparse.Namespace) -> int:
    project = _open_project(args)
    outcome = build_batch(project, args.batch_id)
    _print_outcome(outcome, as_json=args.json)
    return 1 if outcome.status == "FAIL" else 0


def cmd_batch_validate(args: argparse.Namespace) -> int:
    project = _open_project(args)
    outcome = validate_batch(project, args.batch_id)
    _print_outcome(outcome, as_json=args.json)
    return 1 if outcome.status == "FAIL" else 0


def cmd_batch_package(args: argparse.Namespace) -> int:
    project = _open_project(args)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    result = package_batch(project, args.batch_id, output_dir=output_dir)
    if args.json:
        _json_print(result)
    else:
        print(f"Batch {result['batch_id']}: {result['status']}")
        print(f"  archive: {result['archive']}")
        print(f"  bytes: {result['bytes']}")
        print(f"  sha256: {result['sha256']}")
        print(f"  entries: {len(result['entries'])}")
    return 0


def cmd_batch_render(args: argparse.Namespace) -> int:
    project = _open_project(args)
    settings = Settings.from_env(project)
    try:
        report = render_batch(
            project,
            args.batch_id,
            allow_live=args.allow_live,
            settings=settings,
            poll_interval=args.poll_interval,
            timeout_s=args.timeout,
        )
    except ViewMadeBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    if args.json:
        _json_print(report)
    else:
        print(f"Batch render {report['status']}")
        for job in report["jobs"]:
            print(f"  {job.get('package_id')}: {job.get('status')}")
            if job.get("reason"):
                print(f"    {job['reason']}")
            if job.get("error"):
                print(f"    {job['error']}")
    return 0 if report["status"] == "COMPLETE" else 2


def cmd_package_build(args: argparse.Namespace) -> int:
    project = _open_project(args)
    with History(project.history_db, project.history_export) as history:
        result = build_package(project, args.slug, history=history, write=True)
    _print_result(result, as_json=args.json)
    return 1 if result.status == "FAIL" else 0


def cmd_package_validate(args: argparse.Namespace) -> int:
    project = _open_project(args)
    with History(project.history_db, project.history_export) as history:
        result = validate_package_folder(project, args.slug, history=history, write=True)
    _print_result(result, as_json=args.json)
    return 1 if result.status == "FAIL" else 0


def cmd_history_list(args: argparse.Namespace) -> int:
    project = _open_project(args)
    with History(project.history_db, project.history_export) as history:
        topics = history.topics()
        if args.json:
            _json_print([topic.__dict__ for topic in topics])
            return 0
        if not topics:
            print("No topics in history yet.")
            return 0
        print(f"{'id':<30} {'batch':<26} {'status':<7} title")
        for topic in topics:
            print(f"{topic.id:<30} {topic.batch_id:<26} {topic.status:<7} {topic.title}")
    return 0


def cmd_history_check(args: argparse.Namespace) -> int:
    project = _open_project(args)
    package, _research, _folder = project.load_package(args.slug)
    with History(project.history_db, project.history_export) as history:
        matches = history.check_candidate(
            package_id=args.slug,
            slug=args.slug,
            title=str(package.get("title", "")),
            central_question=str(package.get("central_question", "")),
            central_fact=str(package.get("central_fact", "")),
            source_ids=[
                str(source.get("id"))
                for source in project.load_package(args.slug)[1].get("sources", [])
            ],
            batch_id=str(package.get("batch_id", "")),
        )
    if args.json:
        _json_print([match.to_dict() for match in matches])
    elif not matches:
        print("No duplicate or near-duplicate matches.")
    else:
        for match in matches:
            print(
                f"[{match.severity}] {match.reason}: {match.existing_id} "
                f"(similarity {match.similarity:.3f})"
            )
    return 1 if any(match.severity == "FAIL" for match in matches) else 0


def cmd_history_export(args: argparse.Namespace) -> int:
    project = _open_project(args)
    with History(project.history_db, project.history_export) as history:
        path = history.export()
    print(path)
    return 0


def cmd_viewmade_status(args: argparse.Namespace) -> int:
    project = _open_project(args)
    adapter = ViewMadeAdapter(project)
    status = adapter.status()
    if args.json:
        _json_print(status)
        return 0
    print("ViewMade status")
    print(f"  endpoint: {status['endpoint']}")
    print(f"  authenticated: {str(status['authenticated']).lower()}")
    if status.get("expired"):
        print(f"  expired: true (refreshable: {str(status.get('refreshable')).lower()})")
    if status.get("scope"):
        print(f"  scope: {status['scope']}")
    print(f"  token source: {status.get('token_source')}")
    print(f"  tools discovered: {str(status['tools_discovered']).lower()} ({status['tool_count']} tools)")
    print(f"  tools bound: {str(status['bound']).lower()}")
    if not status["authenticated"]:
        print(f"  next: cddocs viewmade login, or connect at {status['connect_url']}")
    elif not status["tools_discovered"]:
        print("  next: cddocs viewmade discover")
    elif not status["bound"]:
        print("  next: cddocs viewmade bind --render-tool ... --status-tool ... --download-tool ...")
    else:
        print("  next: cddocs batch render <batch-id> --allow-live")
    return 0


def cmd_viewmade_login(args: argparse.Namespace) -> int:
    project = _open_project(args)
    from .viewmade import oauth

    result = oauth.login(
        project,
        open_browser=not args.no_browser,
        timeout_s=args.timeout,
        port=args.port,
    )
    if args.json:
        _json_print(result)
    else:
        print("Connected to ViewMade.")
        if result.get("scope"):
            print(f"  scope: {result['scope']}")
        if result.get("expires_at"):
            print(f"  token expires at: {result['expires_at']}")
    return 0


def cmd_viewmade_logout(args: argparse.Namespace) -> int:
    project = _open_project(args)
    from .viewmade import oauth

    result = oauth.logout(project, revoke=not args.no_revoke)
    if not args.keep_binding and project.viewmade_binding_file.is_file():
        project.viewmade_binding_file.unlink()
        result["binding_removed"] = True
    if args.json:
        _json_print(result)
    else:
        print("ViewMade token removed." if result["removed"] else "No local ViewMade token was present.")
        if result.get("revoked"):
            print("  remote token revocation succeeded.")
        for warning in result.get("warnings", []):
            print(f"  warning: {warning}")
        if result.get("binding_removed"):
            print("  tool binding removed.")
    return 0


def cmd_viewmade_discover(args: argparse.Namespace) -> int:
    project = _open_project(args)
    adapter = ViewMadeAdapter(project)
    discovery = adapter.discover()
    if args.json:
        _json_print(discovery)
        return 0
    print(f"Discovered {len(discovery['tools'])} ViewMade MCP tools.")
    print(f"  protocol: {discovery.get('protocol_version')}")
    print(f"  server: {(discovery.get('server_info') or {}).get('name')}")
    for tool in discovery["tools"]:
        schema = tool.get("inputSchema") or {}
        required = schema.get("required") or []
        print(f"  - {tool.get('name')}: {tool.get('description') or ''}")
        if required:
            print(f"      required: {', '.join(str(item) for item in required)}")
    print(f"  saved: {project.viewmade_tools_file}")
    print("  next: bind render/status/download tools explicitly; no render is possible yet.")
    return 0


def cmd_viewmade_tools(args: argparse.Namespace) -> int:
    project = _open_project(args)
    adapter = ViewMadeAdapter(project)
    discovery = adapter.list_discovered_tools()
    if args.json:
        _json_print(discovery)
        return 0
    print(f"{len(discovery.get('tools', []))} discovered tools")
    for tool in discovery.get("tools", []):
        print(f"  - {tool.get('name')}")
        schema = tool.get("inputSchema") or {}
        required = schema.get("required") or []
        if required:
            print(f"      required: {', '.join(str(item) for item in required)}")
    return 0


def _parse_path(value: str) -> list[str]:
    stripped = value.strip()
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("path JSON must be a list of strings")
        return parsed
    return [part for part in stripped.split(".") if part]


def _load_template(path: str | None) -> dict | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("template must be a JSON object")
    return data


def cmd_viewmade_bind(args: argparse.Namespace) -> int:
    project = _open_project(args)
    adapter = ViewMadeAdapter(project)
    templates = {key: dict(value) for key, value in DEFAULT_TEMPLATES.items()}
    for key, path in (
        ("render", args.render_template),
        ("status", args.status_template),
        ("download", args.download_template),
    ):
        loaded = _load_template(path)
        if loaded is not None:
            templates[key] = loaded
    binding = adapter.bind(
        render_tool=args.render_tool,
        status_tool=args.status_tool,
        download_tool=args.download_tool,
        templates=templates,
        job_id_path=_parse_path(args.job_id_path),
        provider_state_path=_parse_path(args.provider_state_path),
        success_states=[item.strip() for item in args.success_states.split(",") if item.strip()],
        failure_states=[item.strip() for item in args.failure_states.split(",") if item.strip()],
        download_url_path=_parse_path(args.download_url_path),
        download_file_path=_parse_path(args.download_file_path),
    )
    if args.json:
        _json_print(binding)
    else:
        print("ViewMade tools bound.")
        for key in ("render", "status", "download"):
            print(f"  {key}: {binding['tools'][key]['name']}")
        print(f"  saved: {project.viewmade_binding_file}")
        print("  render remains disabled until `batch render --allow-live` with CDDOCS_LIVE_CONFIRM=YES.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    project = _open_project(args)
    problems: list[str] = []
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            problems.append(f"{name}: {detail}")

    check("python", sys.version_info >= (3, 10), sys.version.split()[0])
    try:
        channel = project.channel()
        check("channel config", True, f"{channel['channel_name']} / {channel['format']['aspect_ratio']}")
    except Exception as exc:
        check("channel config", False, str(exc))
    try:
        project.sources()
        check("source policy", True, "loaded")
    except Exception as exc:
        check("source policy", False, str(exc))
    try:
        project.viewmade()
        check("viewmade config", True, "loaded; live rendering still requires OAuth and binding")
    except Exception as exc:
        check("viewmade config", False, str(exc))
    packages = project.package_folders()
    batches = project.batch_folders()
    check("content", bool(packages), f"{len(packages)} packages, {len(batches)} batches")
    try:
        with History(project.history_db, project.history_export) as history:
            summary = history.summary()
        check("history", True, f"{summary['topics']} topics in {summary['batches']} batches")
    except Exception as exc:
        check("history", False, str(exc))
    adapter = ViewMadeAdapter(project)
    status = adapter.status()
    check("viewmade auth", bool(status["authenticated"]), status.get("token_source") or "none")
    check("viewmade bindings", bool(status["bound"]), "render/status/download bound" if status["bound"] else "not bound")
    if args.json:
        _json_print({"ok": not problems, "checks": checks, "viewmade": status})
    else:
        print("Doctor")
        for item in checks:
            marker = "OK" if item["ok"] else "FAIL"
            print(f"  [{marker}] {item['check']}: {item['detail']}")
        print()
        if problems:
            print("Blocking problems:")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print("No blocking local problems. Live rendering still needs explicit OAuth and --allow-live.")
    return 0 if not problems else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cddocs",
        description="Evidence-first cats-and-dogs documentary Shorts pipeline.",
    )
    parser.add_argument(
        "--root",
        help="Project root containing config/channel.json. Defaults to the nearest parent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check local configuration and integration state")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    batch = sub.add_parser("batch", help="Batch build, validate, render, or package")
    batch_sub = batch.add_subparsers(dest="batch_command", required=True)
    batch_build = batch_sub.add_parser("build", help="Build all generated artifacts and QA reports")
    batch_build.add_argument("batch_id")
    batch_build.add_argument("--json", action="store_true")
    batch_build.set_defaults(func=cmd_batch_build)
    batch_validate = batch_sub.add_parser("validate", help="Validate existing generated artifacts")
    batch_validate.add_argument("batch_id")
    batch_validate.add_argument("--json", action="store_true")
    batch_validate.set_defaults(func=cmd_batch_validate)
    batch_package = batch_sub.add_parser("package", help="Create a YouTube-ready ZIP archive")
    batch_package.add_argument("batch_id")
    batch_package.add_argument("--output-dir")
    batch_package.add_argument("--json", action="store_true")
    batch_package.set_defaults(func=cmd_batch_package)
    batch_render = batch_sub.add_parser("render", help="Submit to ViewMade through bound official MCP tools")
    batch_render.add_argument("batch_id")
    batch_render.add_argument("--allow-live", action="store_true")
    batch_render.add_argument("--poll-interval", type=float, default=5.0)
    batch_render.add_argument("--timeout", type=float, default=900.0)
    batch_render.add_argument("--json", action="store_true")
    batch_render.set_defaults(func=cmd_batch_render)

    package = sub.add_parser("package", help="Build or validate one package")
    package_sub = package.add_subparsers(dest="package_command", required=True)
    package_build = package_sub.add_parser("build")
    package_build.add_argument("slug")
    package_build.add_argument("--json", action="store_true")
    package_build.set_defaults(func=cmd_package_build)
    package_validate = package_sub.add_parser("validate")
    package_validate.add_argument("slug")
    package_validate.add_argument("--json", action="store_true")
    package_validate.set_defaults(func=cmd_package_validate)

    history = sub.add_parser("history", help="Inspect and check topic history")
    history_sub = history.add_subparsers(dest="history_command", required=True)
    history_list = history_sub.add_parser("list")
    history_list.add_argument("--json", action="store_true")
    history_list.set_defaults(func=cmd_history_list)
    history_check = history_sub.add_parser("check")
    history_check.add_argument("slug")
    history_check.add_argument("--json", action="store_true")
    history_check.set_defaults(func=cmd_history_check)
    history_export = history_sub.add_parser("export")
    history_export.set_defaults(func=cmd_history_export)

    viewmade = sub.add_parser("viewmade", help="Official ViewMade OAuth and MCP operations")
    viewmade_sub = viewmade.add_subparsers(dest="viewmade_command", required=True)
    vm_status = viewmade_sub.add_parser("status")
    vm_status.add_argument("--json", action="store_true")
    vm_status.set_defaults(func=cmd_viewmade_status)
    vm_login = viewmade_sub.add_parser("login")
    vm_login.add_argument("--no-browser", action="store_true")
    vm_login.add_argument("--port", type=int)
    vm_login.add_argument("--timeout", type=float, default=300.0)
    vm_login.add_argument("--json", action="store_true")
    vm_login.set_defaults(func=cmd_viewmade_login)
    vm_logout = viewmade_sub.add_parser("logout")
    vm_logout.add_argument("--no-revoke", action="store_true")
    vm_logout.add_argument("--keep-binding", action="store_true")
    vm_logout.add_argument("--json", action="store_true")
    vm_logout.set_defaults(func=cmd_viewmade_logout)
    vm_discover = viewmade_sub.add_parser("discover")
    vm_discover.add_argument("--json", action="store_true")
    vm_discover.set_defaults(func=cmd_viewmade_discover)
    vm_tools = viewmade_sub.add_parser("tools")
    vm_tools.add_argument("--json", action="store_true")
    vm_tools.set_defaults(func=cmd_viewmade_tools)
    vm_bind = viewmade_sub.add_parser("bind")
    vm_bind.add_argument("--render-tool", required=True)
    vm_bind.add_argument("--status-tool", required=True)
    vm_bind.add_argument("--download-tool", required=True)
    vm_bind.add_argument("--render-template", help="JSON file with render tool arguments")
    vm_bind.add_argument("--status-template", help="JSON file with status tool arguments")
    vm_bind.add_argument("--download-template", help="JSON file with download tool arguments")
    vm_bind.add_argument("--job-id-path", default="job_id")
    vm_bind.add_argument("--provider-state-path", default="status")
    vm_bind.add_argument("--success-states", default="complete,completed,succeeded,success,ready,done")
    vm_bind.add_argument("--failure-states", default="failed,error,cancelled,canceled,rejected")
    vm_bind.add_argument("--download-url-path", default="url")
    vm_bind.add_argument("--download-file-path", default="path")
    vm_bind.add_argument("--json", action="store_true")
    vm_bind.set_defaults(func=cmd_viewmade_bind)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ViewMadeBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    except (OAuthError, MCPError) as exc:
        print(f"ViewMade error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        from .util import PipelineError

        if isinstance(exc, PipelineError):
            print(f"error: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
