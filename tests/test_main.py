from __future__ import annotations

import json

import gha_tray_monitor.__main__ as main_module
from gha_tray_monitor.models import (
    AggregateState,
    AppConfig,
    BuildConfig,
    BuildState,
    BuildStatus,
    ShowBuilds,
)
from gha_tray_monitor.monitor import MonitorSnapshot


class FakeMonitor:
    def __init__(self, _config: AppConfig, snapshot: MonitorSnapshot) -> None:
        self._snapshot = snapshot

    def refresh(self) -> MonitorSnapshot:
        return self._snapshot

    def close(self) -> None:
        return None


def _app_config() -> AppConfig:
    builds = [
        BuildConfig(name="Zulu", url="https://example.com/zulu"),
        BuildConfig(name="Alpha", url="https://example.com/alpha"),
        BuildConfig(name="Beta", url="https://example.com/beta"),
        BuildConfig(name="Delta", url="https://example.com/delta"),
    ]
    return AppConfig(
        poll_interval_seconds=60,
        github_token_env="GITHUB_TOKEN",
        builds=builds,
        show_builds=ShowBuilds.ALL,
    )


def _snapshot(config: AppConfig) -> MonitorSnapshot:
    by_name = {b.name: b for b in config.builds}
    return MonitorSnapshot(
        aggregate_state=AggregateState.RED,
        statuses=[
            BuildStatus(by_name["Zulu"], BuildState.SUCCESS, "success", by_name["Zulu"].url, None),
            BuildStatus(by_name["Beta"], BuildState.FAILED, "failure", by_name["Beta"].url, None),
            BuildStatus(by_name["Delta"], BuildState.RUNNING, "in_progress", by_name["Delta"].url, None),
            BuildStatus(by_name["Alpha"], BuildState.FAILED, "failure", by_name["Alpha"].url, None),
        ],
    )


def test_check_once_show_all_orders_failed_first(monkeypatch, capsys) -> None:
    config = _app_config()
    snapshot = _snapshot(config)

    monkeypatch.setattr(main_module, "load_config", lambda _path: config)
    monkeypatch.setattr(main_module, "BuildMonitor", lambda cfg: FakeMonitor(cfg, snapshot))

    exit_code = main_module._check_once(None, "all", json_output=False)
    output = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 2
    assert output[0] == "overall=red"
    assert output[1:] == [
        "- Alpha: failed (failure)",
        "- Beta: failed (failure)",
        "- Delta: running (in_progress)",
        "- Zulu: success (success)",
    ]


def test_check_once_json_orders_failed_first(monkeypatch, capsys) -> None:
    config = _app_config()
    snapshot = _snapshot(config)

    monkeypatch.setattr(main_module, "load_config", lambda _path: config)
    monkeypatch.setattr(main_module, "BuildMonitor", lambda cfg: FakeMonitor(cfg, snapshot))

    exit_code = main_module._check_once(None, "all", json_output=True)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert [item["name"] for item in payload["builds"]] == [
        "Alpha",
        "Beta",
        "Delta",
        "Zulu",
    ]


def test_check_once_failed_running_orders_failed_first(monkeypatch, capsys) -> None:
    config = _app_config()
    snapshot = _snapshot(config)

    monkeypatch.setattr(main_module, "load_config", lambda _path: config)
    monkeypatch.setattr(main_module, "BuildMonitor", lambda cfg: FakeMonitor(cfg, snapshot))

    exit_code = main_module._check_once(None, "failed+running", json_output=False)
    output = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 2
    assert output[1:] == [
        "- Alpha: failed (failure)",
        "- Beta: failed (failure)",
        "- Delta: running (in_progress)",
    ]

