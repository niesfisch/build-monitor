from gha_tray_monitor.models import AggregateState, AppConfig, BuildConfig, BuildState, BuildStatus
from gha_tray_monitor.monitor import BuildMonitor


class FakeGitHubClient:
    def __init__(self, statuses: list[BuildStatus]) -> None:
        self._statuses = statuses

    def latest_status(self, build: BuildConfig) -> BuildStatus:
        for status in self._statuses:
            if status.config.name == build.name:
                return status
        raise AssertionError("status not found")

    def close(self) -> None:
        return None


def test_aggregate_green_when_all_success() -> None:
    build_a = BuildConfig(name="A", url="https://example.com/a")
    build_b = BuildConfig(name="B", url="https://example.com/b")
    app_config = AppConfig(poll_interval_seconds=60, github_token_env="GITHUB_TOKEN", builds=[build_a, build_b])

    statuses = [
        BuildStatus(build_a, BuildState.SUCCESS, "success", build_a.url, None),
        BuildStatus(build_b, BuildState.SUCCESS, "success", build_b.url, None),
    ]

    monitor = BuildMonitor(app_config, github_client=FakeGitHubClient(statuses))
    snapshot = monitor.refresh()

    assert snapshot.aggregate_state == AggregateState.GREEN


def test_aggregate_red_when_any_failed() -> None:
    build_a = BuildConfig(name="A", url="https://example.com/a")
    build_b = BuildConfig(name="B", url="https://example.com/b")
    app_config = AppConfig(poll_interval_seconds=60, github_token_env="GITHUB_TOKEN", builds=[build_a, build_b])

    statuses = [
        BuildStatus(build_a, BuildState.SUCCESS, "success", build_a.url, None),
        BuildStatus(build_b, BuildState.FAILED, "failure", build_b.url, None),
    ]

    monitor = BuildMonitor(app_config, github_client=FakeGitHubClient(statuses))
    snapshot = monitor.refresh()

    assert snapshot.aggregate_state == AggregateState.RED

