#!/usr/bin/env bash
# Usage: bash tests/preview.sh [missing|ready|no-qr|offline|error]
set -euo pipefail
collie_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
collie_preview=$(mktemp -d /tmp/collie-lab.XXXXXX)
trap 'rm -rf -- "$collie_preview"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$collie_preview/Collie/scripts"
cp "$collie_root/ColliePanel.qml" "$collie_root/IpcOwner.js" "$collie_preview/Collie/"
cp "$collie_root/tests/fixture_control.py" "$collie_preview/Collie/scripts/control.py"
cp "$collie_root/tests/preview.qml" "$collie_preview/shell.qml"
for module in Commons Ui Common; do
  ln -s "/usr/share/omarchy/shell/$module" "$collie_preview/$module"
done
export COLLIE_LAB_FIXTURE="$collie_preview/state.json"
export COLLIE_LAB_HELPER="$collie_root/scripts/control.py"
export COLLIE_LAB_SCENARIO="${1:-missing}"
export QT_QUICK_CONTROLS_STYLE=Basic
printf 'Preview: %s\nActions are simulated; no installation or service changes.\n' "$collie_preview"
qs -p "$collie_preview/shell.qml" --no-color
