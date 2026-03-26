from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gha_tray_monitor.models import AggregateState, AppConfig, BuildConfig, BuildState, BuildStatus
from gha_tray_monitor.monitor import MonitorSnapshot
from gha_tray_monitor.tray_app import (
    TrayApplication,
    _label_for_status,
    _refresh_tooltip,
    _tooltip_for_state,
)


class BlockingMonitor:
    def __init__(
        self,
        snapshot: MonitorSnapshot,
        started: threading.Event,
        release: threading.Event,
        calls: list[str],
    ) -> None:
        self._snapshot = snapshot
        self._started = started
        self._release = release
        self._calls = calls

    def refresh(self) -> MonitorSnapshot:
        self._calls.append("refresh")
        self._started.set()
        self._release.wait(timeout=1)
        return self._snapshot

    def close(self) -> None:
        self._calls.append("close")


class ImmediateMonitor:
    def __init__(self, snapshot: MonitorSnapshot, calls: list[str]) -> None:
        self._snapshot = snapshot
        self._calls = calls

    def refresh(self) -> MonitorSnapshot:
        self._calls.append("refresh")
        return self._snapshot

    def close(self) -> None:
        self._calls.append("close")


def _app_config() -> AppConfig:
    return AppConfig(
        poll_interval_seconds=60,
        github_token_env="GITHUB_TOKEN",
        builds=[BuildConfig(name="Build", url="https://example.com/workflow")],
    )


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


def test_refresh_blinks_while_work_is_running(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    snapshot = MonitorSnapshot(aggregate_state=AggregateState.GREEN, statuses=[])

    monkeypatch.setattr("gha_tray_monitor.tray_app.load_config", lambda _path: _app_config())
    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )

    tray = TrayApplication(
        monitor_factory=lambda _config: BlockingMonitor(snapshot, started, release, calls)
    )

    tray.refresh()
    _wait_for(started.is_set)

    assert tray._refresh_in_progress is True
    assert tray._blink_timer.isActive() is True
    assert tray._refresh_action.isEnabled() is False
    assert tray._tray.toolTip() == _refresh_tooltip()

    release.set()
    _wait_for(lambda: not tray._refresh_in_progress)

    assert tray._refresh_action.isEnabled() is True
    assert tray._blink_timer.isActive() is False
    assert tray._tray.toolTip() == _tooltip_for_state(AggregateState.GREEN)
    assert calls == ["refresh", "close"]

    tray.quit()
    app.processEvents()


def test_refresh_ignores_overlapping_requests(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    snapshot = MonitorSnapshot(aggregate_state=AggregateState.YELLOW, statuses=[])

    monkeypatch.setattr("gha_tray_monitor.tray_app.load_config", lambda _path: _app_config())
    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )

    tray = TrayApplication(
        monitor_factory=lambda _config: BlockingMonitor(snapshot, started, release, calls)
    )

    tray.refresh()
    _wait_for(started.is_set)
    tray.refresh()

    release.set()
    _wait_for(lambda: not tray._refresh_in_progress)

    assert calls == ["refresh", "close"]
    assert tray._tray.toolTip() == _tooltip_for_state(AggregateState.YELLOW)

    tray.quit()
    app.processEvents()


def test_refresh_result_updates_icon_state_and_tooltip(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    calls: list[str] = []
    snapshot = MonitorSnapshot(aggregate_state=AggregateState.RED, statuses=[])

    monkeypatch.setattr("gha_tray_monitor.tray_app.load_config", lambda _path: _app_config())
    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )

    tray = TrayApplication(
        monitor_factory=lambda _config: ImmediateMonitor(snapshot, calls)
    )

    tray.refresh()
    _wait_for(lambda: not tray._refresh_in_progress)

    assert tray._last_aggregate_state == AggregateState.RED
    assert tray._tray.toolTip() == _tooltip_for_state(AggregateState.RED)
    assert tray._refresh_action.isEnabled() is True
    assert calls == ["refresh", "close"]

    tray.quit()
    app.processEvents()


def test_menu_lists_builds_below_static_actions(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    calls: list[str] = []
    build_a = BuildConfig(name="Build A", url="https://example.com/workflow-a")
    build_b = BuildConfig(name="Build B", url="https://example.com/workflow-b")
    snapshot = MonitorSnapshot(
        aggregate_state=AggregateState.YELLOW,
        statuses=[
            BuildStatus(build_a, BuildState.RUNNING, "in_progress", "https://example.com/run-a", None),
            BuildStatus(build_b, BuildState.FAILED, "failure", "https://example.com/run-b", None),
        ],
    )

    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.load_config",
        lambda _path: AppConfig(
            poll_interval_seconds=60,
            github_token_env="GITHUB_TOKEN",
            builds=[build_a, build_b],
        ),
    )
    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )

    tray = TrayApplication(monitor_factory=lambda _config: ImmediateMonitor(snapshot, calls))

    tray.refresh()
    _wait_for(lambda: not tray._refresh_in_progress)

    action_texts = [action.text() for action in tray._menu.actions()]
    assert action_texts == [
        "Refresh now",
        "Quit",
        "",
        _label_for_status(snapshot.statuses[1]),
        _label_for_status(snapshot.statuses[0]),
    ]

    tray.quit()
    app.processEvents()


def test_build_menu_item_opens_browser(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    calls: list[str] = []
    opened_urls: list[str] = []
    build = BuildConfig(name="Build", url="https://example.com/workflow")
    snapshot = MonitorSnapshot(
        aggregate_state=AggregateState.GREEN,
        statuses=[
            BuildStatus(build, BuildState.SUCCESS, "success", "https://example.com/run", None),
        ],
    )

    monkeypatch.setattr("gha_tray_monitor.tray_app.load_config", lambda _path: _app_config())
    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr("gha_tray_monitor.tray_app.webbrowser.open", opened_urls.append)

    tray = TrayApplication(monitor_factory=lambda _config: ImmediateMonitor(snapshot, calls))

    tray.refresh()
    _wait_for(lambda: not tray._refresh_in_progress)

    build_action = tray._build_actions[0]
    build_action.trigger()

    assert opened_urls == ["https://example.com/run"]

    tray.quit()
    app.processEvents()


def test_menu_sorts_failed_first_then_alphabetical(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    calls: list[str] = []
    build_a = BuildConfig(name="Alpha", url="https://example.com/workflow-alpha")
    build_b = BuildConfig(name="Beta", url="https://example.com/workflow-beta")
    build_c = BuildConfig(name="Zulu", url="https://example.com/workflow-zulu")
    build_d = BuildConfig(name="Delta", url="https://example.com/workflow-delta")

    snapshot = MonitorSnapshot(
        aggregate_state=AggregateState.RED,
        statuses=[
            BuildStatus(build_c, BuildState.SUCCESS, "success", "https://example.com/run-zulu", None),
            BuildStatus(build_b, BuildState.FAILED, "failure", "https://example.com/run-beta", None),
            BuildStatus(build_d, BuildState.RUNNING, "in_progress", "https://example.com/run-delta", None),
            BuildStatus(build_a, BuildState.FAILED, "failure", "https://example.com/run-alpha", None),
        ],
    )

    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.load_config",
        lambda _path: AppConfig(
            poll_interval_seconds=60,
            github_token_env="GITHUB_TOKEN",
            builds=[build_a, build_b, build_c, build_d],
        ),
    )
    monkeypatch.setattr(
        "gha_tray_monitor.tray_app.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )

    tray = TrayApplication(monitor_factory=lambda _config: ImmediateMonitor(snapshot, calls))

    tray.refresh()
    _wait_for(lambda: not tray._refresh_in_progress)

    build_action_texts = [action.text() for action in tray._build_actions]
    expected = [
        _label_for_status(snapshot.statuses[3]),  # Alpha failed
        _label_for_status(snapshot.statuses[1]),  # Beta failed
        _label_for_status(snapshot.statuses[2]),  # Delta running
        _label_for_status(snapshot.statuses[0]),  # Zulu success
    ]

    assert build_action_texts == expected

    tray.quit()
    app.processEvents()


