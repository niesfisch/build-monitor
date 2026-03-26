import gha_tray_monitor.runtime_checks as runtime_checks


def test_preflight_reports_missing_xcb_cursor_for_x11(monkeypatch) -> None:
    monkeypatch.setattr(runtime_checks.platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(runtime_checks.ctypes_util, "find_library", lambda _name: None)

    message = runtime_checks.check_linux_qt_runtime()

    assert message is not None
    assert "libxcb-cursor0" in message


def test_preflight_skips_xcb_check_for_wayland(monkeypatch) -> None:
    monkeypatch.setattr(runtime_checks.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(runtime_checks.ctypes_util, "find_library", lambda _name: None)

    message = runtime_checks.check_linux_qt_runtime()

    assert message is None


def test_preflight_skips_when_library_is_available(monkeypatch) -> None:
    monkeypatch.setattr(runtime_checks.platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(runtime_checks.ctypes_util, "find_library", lambda _name: "libxcb-cursor.so.0")

    message = runtime_checks.check_linux_qt_runtime()

    assert message is None

