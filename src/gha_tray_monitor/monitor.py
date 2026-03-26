from __future__ import annotations

from dataclasses import dataclass

from .github_api import GitHubClient
from .models import AggregateState, AppConfig, BuildState, BuildStatus


@dataclass(slots=True)
class MonitorSnapshot:
    aggregate_state: AggregateState
    statuses: list[BuildStatus]


class BuildMonitor:
    def __init__(self, config: AppConfig, github_client: GitHubClient | None = None) -> None:
        self._config = config
        self._client = github_client or GitHubClient(token_env_name=config.github_token_env)

    def close(self) -> None:
        self._client.close()

    def refresh(self) -> MonitorSnapshot:
        statuses = [self._client.latest_status(build) for build in self._config.builds]
        aggregate = self._aggregate(statuses)
        return MonitorSnapshot(aggregate_state=aggregate, statuses=statuses)

    @staticmethod
    def _aggregate(statuses: list[BuildStatus]) -> AggregateState:
        if not statuses:
            return AggregateState.GRAY

        if any(item.state == BuildState.FAILED for item in statuses):
            return AggregateState.RED

        if all(item.state == BuildState.SUCCESS for item in statuses):
            return AggregateState.GREEN

        if any(item.state in {BuildState.RUNNING, BuildState.UNKNOWN} for item in statuses):
            return AggregateState.YELLOW

        return AggregateState.GRAY

