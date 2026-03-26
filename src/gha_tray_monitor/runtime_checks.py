from __future__ import annotations

import os
import platform
from ctypes import util as ctypes_util


def _uses_xcb_backend() -> bool:
    forced_backend = os.getenv("QT_QPA_PLATFORM", "").strip().lower()
    if forced_backend:
        return forced_backend == "xcb"

    if os.getenv("DISPLAY"):
        return True

    if os.getenv("WAYLAND_DISPLAY"):
        return False

    return False


def check_linux_qt_runtime() -> str | None:
    if platform.system() != "Linux":
        return None

    if not _uses_xcb_backend():
        return None

    if ctypes_util.find_library("xcb-cursor"):
        return None

    return (
        "Missing Qt runtime dependency: xcb-cursor.\n"
        "Install it and start the app again.\n"
        "Ubuntu/Debian: sudo apt install -y libxcb-cursor0\n"
        "Fedora: sudo dnf install -y xcb-util-cursor\n"
        "Arch: sudo pacman -S xcb-util-cursor\n"
        "openSUSE: sudo zypper install -y libxcb-cursor0"
    )

