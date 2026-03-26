#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
LINK_BIN="$HOME/.local/bin/gha-tray-monitor"
TARGET_BIN="$VENV_DIR/bin/gha-tray-monitor"

echo "=== Ensuring project virtualenv..."
if [[ ! -x "$VENV_PYTHON" ]]; then
  python3 -m venv "$VENV_DIR"
fi

cd "$PROJECT_DIR"

echo ""
echo "=== Installing build tools into virtualenv..."
"$VENV_PYTHON" -m pip install --upgrade pip build

echo ""
echo "=== Building wheel..."
rm -f dist/*.whl
"$VENV_PYTHON" -m build

echo ""
echo "=== Installing wheel into virtualenv..."
"$VENV_PIP" install --force-reinstall dist/*.whl

if [[ ! -x "$TARGET_BIN" ]]; then
  echo "ERROR: Expected launcher not found after install: $TARGET_BIN"
  exit 1
fi

echo ""
echo "=== Refreshing launcher symlink..."
mkdir -p "$HOME/.local/bin"
ln -sfn "$TARGET_BIN" "$LINK_BIN"
echo "Linked $LINK_BIN -> $TARGET_BIN"

echo ""
echo "=== Reloading systemd and restarting service..."
systemctl --user daemon-reload
systemctl --user restart gha-tray-monitor.service

echo ""
echo "=== Service status..."
systemctl --user status gha-tray-monitor.service

echo ""
echo "✓ Done! Service is now running with the latest code."

