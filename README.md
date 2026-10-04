# Collie Control for Omarchy

A small native Quickshell bar widget for [Collie](https://colliepwa.dev/), the mobile frontend for Herdr. It shows whether the bridge is answering and whether its tailnet proxy is configured, and uses the official `collie` CLI for every service action.

```bash
omarchy plugin add https://github.com/overp0werj0int/omarchy-collie --enable
```

Requires Omarchy Quattro, Python 3, Tailscale, and a configured Collie installation. Opening uses `xdg-open`; copying uses `wl-copy`. The widget installs no packages, changes no Collie configuration and requires no root privileges.

## Controls

| Input | Action |
| --- | --- |
| Left click | Open controls and status |
| Middle click | Open Collie in your browser |
| Right click | Start or stop the Collie service |
| Panel | Open, copy URL, start/stop, restart, publish tailnet access, pair device, diagnostics |
| Tab / Enter / Escape | Navigate controls, activate, close |

The dog icon is dimmed when the bridge is down. Its dot uses the theme accent when the bridge is healthy and its tailnet mapping exists, and the urgent color when the bridge is healthy but the mapping is missing. This checks the local service and proxy configuration; it does not claim to test another device's tailnet connection.

Pair a device generates a single-use code valid for ten minutes. Enter it in Collie's Settings → Paired devices on your phone. It is displayed in the popup and cleared after expiry; no pairing credential or account identity is stored in the widget.

## Install Collie on Arch / Omarchy

Follow [Collie's official install guide](https://colliepwa.dev/install). Its official package is currently built from its own PKGBUILD:

```bash
git clone https://github.com/AltanS/collie.git
cd collie/packaging/aur
makepkg -si
herdr plugin link /opt/collie  # optional: expose Collie's actions in Herdr
```

Create the configuration at `~/.config/herdr/plugins/config/herdr.collie/.env` on a host running Herdr. A minimal setup is:

```dotenv
COLLIE_MUX=herdr
COLLIE_HOST=127.0.0.1
COLLIE_PORT=8787
COLLIE_TRUSTED_USER=you@example.com
```

Set `COLLIE_TRUSTED_USER` to your actual Tailscale login, keep this file private, then run `collie start`. It manages a `systemd --user` service and a Tailscale Serve proxy. The default uses HTTPS, which requires HTTPS certificates enabled in your tailnet. It supports full PWA installation and Web Push.

For HTTP inside an encrypted tailnet, without issuing public certificates, add these settings instead:

```dotenv
COLLIE_SERVE_MODE=http
COLLIE_PUBLIC_HOSTS=your-host.your-tailnet.ts.net,your-tailscale-ip
```

Then run `collie restart`. Your URL is `http://your-host.your-tailnet.ts.net:8787`. HTTP works in a phone browser over Tailscale, but remote HTTP is not a browser secure context: full PWA installation and Web Push require HTTPS. Tailscale Serve restricts ingress to your tailnet and injects the identity header Collie checks. Never use Funnel for this service. See [Collie's security guide](https://colliepwa.dev/security).

To keep the user service available after logout and across reboots:

```bash
loginctl enable-linger "$USER"
```

Collie mirrors an existing Herdr server; this widget never stops Herdr or its agent sessions. Stopping Collie pauses remote access. The official `stop` command leaves its proxy configured; `collie uninstall` removes the service and its owned proxy.

## Widget settings

Settings live inline in the widget's `shell.json` layout entry:

| Setting | Default | Purpose |
| --- | --- | --- |
| `refreshIntervalSec` | `10` | Poll interval, 5–120 seconds |
| `collieBinary` | `collie` | Executable name or absolute path |
| `bridgePort` | `8787` | Local health probe port |

The executable is resolved from PATH with fallbacks to `~/.local/bin/collie` and `~/.local/share/collie/current/bin/collie`. A Herdr source plugin can set `collieBinary` to its `bin/collie` path. The service monitored is the default `collie.service`; named Collie instances are outside this widget's scope.

With Powerbar, keep the widget visible by setting `powerbarVisibility` to `"shown"` in its layout entry. It works on horizontal and vertical bars.

## Development and verification

```bash
omarchy plugin validate .
python3 scripts/control.py status
python3 scripts/control.py doctor
```

The Python helper uses argument arrays, never a shell, and probes only loopback `/api/health`. It does not read terminal contents, sessions or credentials. Status failures and action errors appear in the panel. Collie's own CLI handles configuration, service supervision, authentication and Tailscale proxy ownership.

The widget also exposes IPC methods on `overp0werj0int.collie`: `open`, `close`, `toggle`, `refresh`, `status`, `start`, `stop`, `restart`, `openBrowser`, `copyUrl`, `pairDevice`, `publish`, and `diagnostics`. For example:

```bash
omarchy-shell overp0werj0int.collie status
omarchy-shell overp0werj0int.collie restart
```

This is an independent MIT-licensed widget. Collie and Herdr are their respective projects; no upstream logo or application code is bundled.
