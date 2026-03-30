from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import AppConfig, BuildConfig, ShowBuilds

APP_DIR_NAME = "gha-tray-monitor"
CONFIG_FILE_NAME = "config.json"


def default_config_path() -> Path:
    return Path.home() / ".config" / APP_DIR_NAME / CONFIG_FILE_NAME


def _example_config() -> AppConfig:
    return AppConfig(
        poll_interval_seconds=60,
        github_token_env="GITHUB_TOKEN",
        builds=[
            BuildConfig(
                name="Build Monitor",
                url="https://github.com/niesfisch/build-monitor/actions/workflows/ci.yml",
                branch="main",
            )
        ],
    )


def ensure_config_exists(path: Path) -> None:
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    example = _example_config()
    raw = asdict(example)
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    ensure_config_exists(config_path)

    raw = json.loads(config_path.read_text(encoding="utf-8"))

    poll_interval_seconds = int(raw.get("poll_interval_seconds", 60))
    if poll_interval_seconds < 10:
        raise ValueError("poll_interval_seconds must be >= 10")

    github_token_env = str(raw.get("github_token_env", "GITHUB_TOKEN"))

    builds_raw = raw.get("builds", [])
    if not isinstance(builds_raw, list) or not builds_raw:
        raise ValueError("config must contain a non-empty builds array")

    builds: list[BuildConfig] = []
    for entry in builds_raw:
        if not isinstance(entry, dict):
            raise ValueError("each build entry must be an object")

        name = str(entry.get("name", "")).strip()
        url = str(entry.get("url", "")).strip()
        branch_raw = entry.get("branch")
        branch = str(branch_raw).strip() if branch_raw is not None else None

        if not name or not url:
            raise ValueError("each build entry requires name and url")

        builds.append(BuildConfig(name=name, url=url, branch=branch or None))

    show_builds_raw = str(raw.get("show_builds", ShowBuilds.ALL.value)).strip().lower()
    try:
        show_builds = ShowBuilds(show_builds_raw)
    except ValueError:
        valid = ", ".join(e.value for e in ShowBuilds)
        raise ValueError(f"show_builds must be one of: {valid}")

    return AppConfig(
        poll_interval_seconds=poll_interval_seconds,
        github_token_env=github_token_env,
        builds=builds,
        show_builds=show_builds,
    )

