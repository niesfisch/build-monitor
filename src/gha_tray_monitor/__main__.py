from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
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


def main() -> int:
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

    args = parser.parse_args()

    if args.check_once:
        return _check_once(args.config, args.show, args.json)

    runtime_issue = check_linux_qt_runtime()
    if runtime_issue:
        print(runtime_issue, file=sys.stderr)
        return 3

    try:
        from .tray_app import TrayApplication

        app = TrayApplication(config_path=args.config)
        return app.start()
    except Exception as exc:
        print(f"Failed to start tray app: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

