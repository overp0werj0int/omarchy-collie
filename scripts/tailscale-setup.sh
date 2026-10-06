#!/usr/bin/env bash
# An interactive terminal is needed for package privileges and Tailscale sign-in.
set -euo pipefail
trap 'read -r -p "Press Enter to close…" || true' EXIT
printf 'Collie Lab · Tailscale setup\n\n'
if ! command -v tailscale >/dev/null; then
  omarchy pkg add tailscale
fi
/usr/bin/sudo /usr/bin/systemctl enable --now tailscaled
/usr/bin/sudo /usr/bin/tailscale up
printf '\nTailscale setup complete. Return to Collie Lab to deploy the backend.\n'
