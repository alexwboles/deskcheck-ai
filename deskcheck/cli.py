"""CLI: ``deskcheck run test.yaml`` (exit 0 pass, 1 fail, 2 setup error,
3 interrupted) and ``deskcheck mcp`` (stdio MCP server)."""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from . import __version__
from .errors import DeskcheckError
from .factory import get_driver
from .permissions import PermissionConfig
from .runner import run_test


def _config(path):
    if path:
        return PermissionConfig.from_file(path)
    return PermissionConfig.empty()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="deskcheck",
                                     description="Deterministic desktop-test loop.")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="run a YAML test file")
    run.add_argument("test")
    run.add_argument("--config", default=None, help="allowlist config YAML")
    run.add_argument("--driver", default="mock",
                     choices=["auto", "mock", "linux", "windows"])
    run.add_argument("--mock-windows", default="",
                     help="comma-separated window names for the mock driver")
    run.add_argument("--out-dir", default=None)
    run.add_argument("--max-steps", type=int, default=100)
    run.add_argument("--timeout-ms", type=int, default=30000)
    run.add_argument("--update-baselines", action="store_true",
                     help="accept current screenshots as baselines, then pass")
    mcp = sub.add_parser("mcp", help="run the stdio MCP server")
    mcp.add_argument("--config", default=None)
    mcp.add_argument("--driver", default="mock",
                     choices=["auto", "mock", "linux", "windows"])
    mcp.add_argument("--workspace", default=os.getcwd())
    mcp.add_argument("--allow-baseline-updates", action="store_true")
    sub.add_parser("gui", help="open the desktop runner")
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.cmd == "gui":
        from .desktop import main as desktop_main
        desktop_main()
        return 0
    if args.cmd == "mcp":
        from .mcp_server import serve
        try:
            serve(config=_config(args.config), driver_name=args.driver,
                  workspace=args.workspace, allow_baseline_updates=args.allow_baseline_updates)
            return 0
        except KeyboardInterrupt:
            return 3
        except (DeskcheckError, OSError, ValueError) as exc:
            print(f"deskcheck: {exc}", file=sys.stderr)
            return 2
    if args.cmd != "run":
        parser.print_help()
        return 2
    try:
        config = _config(args.config)
        mock_windows = [w for w in (args.mock_windows.split(",") if args.mock_windows else [])
                        if w]
        driver = get_driver(args.driver, mock_windows=mock_windows or None)
    except (DeskcheckError, OSError, ValueError) as exc:
        print(f"deskcheck: {exc}", file=sys.stderr)
        return 2
    out_dir = args.out_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.test)),
        "runs", os.path.splitext(os.path.basename(args.test))[0]+"-"+uuid.uuid4().hex[:12])
    try:
        result = run_test(args.test, config, driver, out_dir,
                          update_baselines=args.update_baselines,
                          max_steps=args.max_steps,
                          timeout_ms=args.timeout_ms)
    except (DeskcheckError, OSError, ValueError) as exc:
        print(f"deskcheck: {exc}", file=sys.stderr)
        return 2
    finally:
        driver.close()
    print(f"deskcheck: {result.status} ({result.name}) [driver={result.driver}{'; SIMULATED - no real app tested' if result.driver == 'mock' else ''}] — "
          f"report: {os.path.join(out_dir, 'report.md')}")
    for failure in result.failures:
        print(f"deskcheck: {failure}", file=sys.stderr)
    return {"pass": 0, "fail": 1, "interrupted": 3, "error": 2}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
