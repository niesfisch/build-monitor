from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .config import APP_DIR_NAME, load_config
from .models import BuildState, ShowBuilds, status_sort_key
from .monitor import BuildMonitor
from .runtime_checks import check_linux_qt_runtime


def _check_once(config_path: Path | None, show_override: str | None, json_output: bool = False) -> int:
    config = load_config(config_path)
    monitor = BuildMonitor(config)
    snapshot = monitor.refresh()
    monitor.close()

    # CLI flag beats config
    show = ShowBuilds(show_override) if show_override is not None else config.show_builds

    if show == ShowBuilds.FAILED:
        visible = [s for s in snapshot.statuses if s.state == BuildState.FAILED]
    elif show == ShowBuilds.FAILED_RUNNING:
        visible = [
            s for s in snapshot.statuses
            if s.state in (BuildState.FAILED, BuildState.RUNNING)
        ]
    else:
        visible = list(snapshot.statuses)

    visible = sorted(visible, key=status_sort_key)

    if json_output:
        output = {
            "overall": snapshot.aggregate_state.value,
            "builds": [
                {
                    "name": item.config.name,
                    "state": item.state.value,
                    "summary": item.summary,
                    "url": item.details_url,
                    "updated_at": item.updated_at,
                }
                for item in visible
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"overall={snapshot.aggregate_state.value}")
        if not visible:
            if show == ShowBuilds.FAILED:
                print("no failures :)")
            elif show == ShowBuilds.FAILED_RUNNING:
                print("no failures or active runs :)")
            else:
                print("no builds configured")
        else:
            for item in visible:
                print(f"- {item.config.name}: {item.state.value} ({item.summary})")

    if snapshot.aggregate_state.value == "red":
        return 2
    if snapshot.aggregate_state.value == "yellow":
        return 1
    return 0


def _background_log_path() -> Path:
    state_home_raw = os.environ.get("XDG_STATE_HOME")
    state_home = Path(state_home_raw) if state_home_raw else Path.home() / ".local" / "state"
    log_dir = state_home / APP_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "tray.log"


def _background_command(config_path: Path | None) -> list[str]:
    command = [sys.executable, "-m", "gha_tray_monitor"]
    if config_path is not None:
        command.extend(["--config", str(config_path)])
    return command


def _run_tray(config_path: Path | None) -> int:
    runtime_issue = check_linux_qt_runtime()
    if runtime_issue:
        print(runtime_issue, file=sys.stderr)
        return 3

    try:
        from .tray_app import TrayApplication

        app = TrayApplication(config_path=config_path)
        return app.start()
    except Exception as exc:
        print(f"Failed to start tray app: {exc}", file=sys.stderr)
        return 1


def _start_in_background(config_path: Path | None) -> int:
    runtime_issue = check_linux_qt_runtime()
    if runtime_issue:
        print(runtime_issue, file=sys.stderr)
        return 3

    log_path = _background_log_path()

    try:
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write("\n=== gha-tray-monitor background start ===\n")
            log_file.flush()
            process = subprocess.Popen(
                _background_command(config_path),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        print(f"Failed to start background tray app: {exc}", file=sys.stderr)
        return 1

    time.sleep(0.2)
    return_code = process.poll()
    if return_code is not None:
        print(
            f"Background tray app exited immediately with code {return_code}. Check {log_path}.",
            file=sys.stderr,
        )
        return return_code or 1

    print(f"Started tray app in background (pid {process.pid}). Logs: {log_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub Actions tray monitor")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a JSON config file. Defaults to ~/.config/gha-tray-monitor/config.json",
    )
    parser.add_argument(
        "--check-once",
        action="store_true",
        help="Fetch statuses once and print them to stdout.",
    )
    parser.add_argument(
        "--show",
        choices=[e.value for e in ShowBuilds],
        default=None,
        metavar="FILTER",
        help=(
            "Which builds to print in --check-once mode. "
            "Choices: all | failed | failed+running. "
            "Overrides show_builds in config.json."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for --check-once mode).",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Start the tray app in the background and return to the shell.",
    )

    args = parser.parse_args(argv)

    if args.check_once:
        if args.background:
            print("--background cannot be combined with --check-once", file=sys.stderr)
            return 2
        return _check_once(args.config, args.show, args.json)

    if args.background:
        return _start_in_background(args.config)

    return _run_tray(args.config)


if __name__ == "__main__":
    raise SystemExit(main())

