from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BuildState(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    UNKNOWN = "unknown"


class AggregateState(str, Enum):
    GREEN = "green"
    RED = "red"
    YELLOW = "yellow"
    GRAY = "gray"


class ShowBuilds(str, Enum):
    """Controls which builds are printed in --check-once mode."""

    ALL = "all"
    FAILED = "failed"
    FAILED_RUNNING = "failed+running"


@dataclass(slots=True)
class BuildConfig:
    name: str
    url: str
    branch: str | None = None


@dataclass(slots=True)
class AppConfig:
    poll_interval_seconds: int
    github_token_env: str
    builds: list[BuildConfig]
    show_builds: ShowBuilds = ShowBuilds.ALL


@dataclass(slots=True)
class BuildStatus:
    config: BuildConfig
    state: BuildState
    summary: str
    details_url: str
    updated_at: str | None


def status_sort_key(status: BuildStatus) -> tuple[int, str]:
    """Sort failed builds first, then alphabetically by build name."""

    failed_rank = 0 if status.state == BuildState.FAILED else 1
    return (failed_rank, status.config.name.casefold())


