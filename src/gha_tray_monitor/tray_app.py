from __future__ import annotations

import sys
import threading
import webbrowser
from queue import Empty, Queue
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import load_config
from .models import AggregateState, AppConfig, BuildState, BuildStatus, status_sort_key
from .monitor import BuildMonitor, MonitorSnapshot

ICON_SIZE = 22


def _icon_for_state(state: AggregateState) -> QIcon:
    color_map = {
        AggregateState.GREEN: QColor("#2ecc71"),
        AggregateState.RED: QColor("#e74c3c"),
        AggregateState.YELLOW: QColor("#f1c40f"),
        AggregateState.GRAY: QColor("#7f8c8d"),
    }

    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color_map[state])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, ICON_SIZE - 4, ICON_SIZE - 4)
    painter.end()

    return QIcon(pixmap)


def _tooltip_for_state(state: AggregateState) -> str:
    return f"GitHub Actions Build Monitor ({state.value})"


def _refresh_tooltip() -> str:
    return "GitHub Actions Build Monitor (refreshing...)"


def _label_for_status(status: BuildStatus) -> str:
    symbol = {
        BuildState.FAILED: "❌",
        BuildState.SUCCESS: "✅",
        BuildState.RUNNING: "🟡",
        BuildState.UNKNOWN: "❔",
    }[status.state]
    return f"{symbol} {status.config.name}"


class TrayApplication:
    def __init__(
        self,
        config_path: Path | None = None,
        monitor_factory: Callable[[AppConfig], BuildMonitor] | None = None,
    ) -> None:
        self._app = QApplication.instance() or QApplication(sys.argv)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            raise RuntimeError("No system tray detected in this desktop session")

        self._config_path = config_path
        self._config = load_config(config_path)
        self._monitor_factory = monitor_factory or BuildMonitor
        self._tray = QSystemTrayIcon()
        self._menu = QMenu()
        self._last_aggregate_state = AggregateState.GRAY
        self._last_snapshot: MonitorSnapshot | None = None
        self._refresh_in_progress = False
        self._blink_visible = False
        self._refresh_results: Queue[tuple[str, MonitorSnapshot | Exception]] = Queue()
        self._build_separator: QAction | None = None
        self._build_actions: list[QAction] = []

        self._refresh_action = QAction("Refresh now")
        self._refresh_action.triggered.connect(self.refresh)

        self._reload_config_action = QAction("Reload config")
        self._reload_config_action.triggered.connect(self.reload_config)

        self._quit_action = QAction("Quit")
        self._quit_action.triggered.connect(self.quit)

        self._menu.addAction(self._refresh_action)
        self._menu.addAction(self._reload_config_action)
        self._menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.setToolTip(_tooltip_for_state(self._last_aggregate_state))

        self._blink_timer = QTimer()
        self._blink_timer.setInterval(350)
        self._blink_timer.timeout.connect(self._toggle_refresh_icon)

        self._refresh_result_timer = QTimer()
        self._refresh_result_timer.setInterval(100)
        self._refresh_result_timer.timeout.connect(self._consume_refresh_result)

        self._timer = QTimer()
        self._timer.timeout.connect(self.refresh)
        self._timer.start(self._config.poll_interval_seconds * 1000)

    def start(self) -> int:
        self._tray.show()
        self.refresh()
        return self._app.exec()

    def quit(self) -> None:
        self._timer.stop()
        self._blink_timer.stop()
        self._refresh_result_timer.stop()
        self._tray.hide()
        self._app.quit()

    def refresh(self) -> None:
        if self._refresh_in_progress:
            return

        self._refresh_in_progress = True
        self._refresh_action.setEnabled(False)
        self._tray.setToolTip(_refresh_tooltip())
        self._blink_visible = False
        self._blink_timer.start()
        self._toggle_refresh_icon()
        self._refresh_result_timer.start()

        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def reload_config(self) -> None:
        try:
            self._config = load_config(self._config_path)
            self._timer.setInterval(self._config.poll_interval_seconds * 1000)
            self.refresh()
        except Exception as exc:
            self._last_aggregate_state = AggregateState.YELLOW
            self._tray.setIcon(_icon_for_state(self._last_aggregate_state))
            self._tray.setToolTip(f"Config error: {exc}")


    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._menu.popup(QPoint(QCursor.pos().x(), QCursor.pos().y()))

    def _toggle_refresh_icon(self) -> None:
        self._blink_visible = not self._blink_visible
        blink_state = AggregateState.YELLOW if self._blink_visible else AggregateState.GRAY
        self._tray.setIcon(_icon_for_state(blink_state))

    def _refresh_worker(self) -> None:
        monitor = self._monitor_factory(self._config)
        try:
            snapshot = monitor.refresh()
            self._refresh_results.put(("snapshot", snapshot))
        except Exception as exc:
            self._refresh_results.put(("error", exc))
        finally:
            monitor.close()

    def _consume_refresh_result(self) -> None:
        try:
            result_type, payload = self._refresh_results.get_nowait()
        except Empty:
            return

        self._blink_timer.stop()
        self._refresh_result_timer.stop()
        self._refresh_in_progress = False
        self._refresh_action.setEnabled(True)

        if result_type == "snapshot":
            snapshot = payload
            assert isinstance(snapshot, MonitorSnapshot)
            self._last_snapshot = snapshot
            self._last_aggregate_state = snapshot.aggregate_state
            self._rebuild_build_menu(snapshot)
        else:
            self._last_aggregate_state = AggregateState.YELLOW
            self._rebuild_build_menu(None)

        self._tray.setIcon(_icon_for_state(self._last_aggregate_state))
        self._tray.setToolTip(_tooltip_for_state(self._last_aggregate_state))

    def _rebuild_build_menu(self, snapshot: MonitorSnapshot | None) -> None:
        for action in self._build_actions:
            self._menu.removeAction(action)
        self._build_actions.clear()

        if self._build_separator is not None:
            self._menu.removeAction(self._build_separator)
            self._build_separator = None

        if snapshot is None or not snapshot.statuses:
            return

        self._build_separator = self._menu.addSeparator()

        for status in sorted(snapshot.statuses, key=status_sort_key):
            action = QAction(_label_for_status(status), self._menu)
            target_url = status.details_url or status.config.url
            action.triggered.connect(
                lambda _checked=False, url=target_url: webbrowser.open(url)
            )
            self._menu.addAction(action)
            self._build_actions.append(action)


