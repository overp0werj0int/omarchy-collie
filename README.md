# Collie Lab for Omarchy

A native Quickshell control panel for [Collie](https://colliepwa.dev/), the mobile frontend for Herdr, tmux, and zellij. Install the backend from the widget, see what is ready, and scan a QR code to connect your phone.

```bash
omarchy plugin add https://github.com/overp0werj0int/omarchy-collie --enable
```

Requires Omarchy Quattro and Python 3.12 or later. The panel detects the remaining requirements and offers actions to install or connect them. Curl is required for health checks and downloads; qrencode is required for QR images. Other commands used are Tailscale, systemctl, pkexec/pacman, sudo (only in the setup terminal), xdg-open, wl-copy, and the selected backend CLI.

## First connection

1. Click the dog in the bar. Collie Lab lists what is left: **Requirements**, **Tailscale**, **Collie bridge** and **Private address**. Pick the workspace to mirror (**Herdr**, **tmux** or **zellij**; Herdr by default).
2. Press **Enter** or select **Set up Collie**. One request finishes every remaining step and stops at the first one that fails:
   - Missing packages (Tailscale, the workspace, `qrencode`, `curl`) install together behind one password prompt.
   - If Tailscale is not signed in, a terminal opens for sign-in. Setup notices the connection within seconds and continues by itself; **Stop waiting** cancels.
   - The widget downloads the reviewed official Collie 1.16.2 release, verifies its repository-pinned SHA-256, checks archive paths and size limits, and installs in your home folder. An existing Collie installation is reused.
   - A new configuration gets loopback binding, your bridge port, the selected backend and your Tailscale login as `COLLIE_TRUSTED_USER`. Existing `.env` and TOML configurations are preserved. Collie's CLI starts its user service and publishes its own Tailscale Serve route.
   - Setup succeeds only when the local health probe answers and the Serve mapping matches this bridge.
3. The panel switches to **Connect** with two ways in for another device. Nothing is made until you choose:
   - **Watch only** (`w`) shows a QR code with Collie's plain address. Once any device is paired, Collie lets unpaired devices read but not type or approve. Until then the panel says that this link can still type.
   - **Full control** (`f`) makes a one-time pairing code and shows a QR code whose link carries it (`/settings?pair=CODE`), with a large countdown to the code's expiry (the CLI's, at most ten minutes). **New code** (`n`) replaces it at any time; an expired code says so and waits for a new one. Type an optional **Device name** and the same link carries it too (`&name=…`); the QR code is redrawn with the same code, and the countdown keeps running.
   Turn on Tailscale on your phone, signed in to the same tailnet, and scan with the camera.
4. **Open on this computer** (`o`, or middle-click the bar icon) opens Collie in an Omarchy web app window with full control. If no device is paired, Collie gates nothing and the window opens straight in. Otherwise the first time makes a code and opens Collie's pairing form with the code filled in and this computer's host name in the link as its name; press **Pair**. The widget remembers which device that was (`~/.local/state/collie-lab/this-computer.json`), so later opens go straight in. Revoking it with `collie devices revoke` makes the next open pair again.
   > Collie 1.17 fills in the code from the link but does not read `name` yet, so its **Device name** field still starts empty: type a name, then **Pair**. The widget already sends the name, so a Collie that reads it needs nothing typed.
5. Add Collie to the home screen: Safari → Share → Add to Home Screen on iPhone, or Chrome → Install app on Android. Full PWA installation requires HTTPS.

When the bridge later stops or loses its route, the same list reappears under **Get back online** with one button for the next step (**Start bridge**, **Publish to tailnet**, **Connect Tailscale**).

QR codes are generated locally with `qrencode` and held in memory. The widget can install that tool on click if it is missing. Pairing codes and their QR images are cleared when the panel closes, on expiry, when the connection changes, or when the bridge goes offline. Closing the panel clears the displayed code; it does not revoke the pending code on the backend. Each new code replaces the previous pending one. A code being redrawn for a new device name reaches the helper through its environment, never its command line. The IPC status method never returns the pairing code or QR image.

## Backend setup and recovery

The installer uses the [official standalone install flow](https://colliepwa.dev/install), which installs to `~/.local/share/collie` and links `~/.local/bin/collie`, without root. Package-managed or source installations found on PATH are reused. A custom `collieBinary` path that is missing produces an error instead of silently installing another copy.

Package requirements use Arch's package manager with a system authorization prompt. Tailscale setup uses a visible terminal for permissions and sign-in. Installation never runs on widget load or status refresh; it starts only through a button or the explicit `setup` IPC action.

The setup flow is **Check → Install/detect → Configure → Start/publish → Verify**. A lock prevents overlapping setups. Retrying reuses the installed binary and preserves configuration. Closing the popup leaves the action running while the widget remains loaded. Reloading or removing the plugin can interrupt an action; reopening and retrying setup recovers the already completed steps.

If the bridge is online but the route is missing, enable HTTPS in your tailnet and select **Publish to tailnet** (or **Publish** in the Bridge row). Tailscale may require authorization to enable Serve. Errors remain visible with **Try again**, **Show details**, and **Diagnostics**. See [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) and [Collie's install guide](https://colliepwa.dev/install) for configuration-specific recovery.

The readiness indicator verifies local health and the exact proxy configuration. It does not claim to test a phone's Tailscale sign-in, ACLs, DNS, or camera. The phone must share a tailnet that can reach this host. The widget follows Collie's configured URL, including existing HTTP setups; remote HTTP supports a browser tab but lacks full PWA installation and Web Push.

To keep Collie's user service available after logout and across reboots, run:

```bash
loginctl enable-linger "$USER"
```

Stopping Collie pauses remote access and leaves its owned proxy configured. Herdr and its sessions continue running. The widget does not remove backends, services, paired devices, or existing configuration.

## Controls

| Input | Action |
| --- | --- |
| Left click | Open Collie Lab |
| Middle click | Open Collie on this computer when the bridge is healthy |
| Right click | Start or stop an installed bridge |
| Header switch | Start or stop the bridge |
| `Enter` | Run the focused control; on open, that is the next setup step |
| `w` / `f` | Watch only / Full control (press again to hide) |
| `n` | New pairing code (Full control) |
| `c` | Copy the watch-only link |
| `o` | Open Collie on this computer (closes the panel) |
| `s` / `r` / `d` | Start or stop / restart / diagnostics |
| Tab / Shift+Tab | Move between controls; h/l or arrows move within a choice |
| Escape | Leave the name field, then the chosen way in, then close the panel |

The footer shows the keys that apply to the current view. The layout uses your Omarchy palette, typography and panel components (hero, section headers, separators, switch), fits horizontal and vertical bars, and scrolls only on small displays. Success messages fade after a few seconds. Only a failed action you started shows in red, with **Try again**, **Show details** and **Diagnostics**; it clears when the panel closes. Background issues (a missed status poll, a pairing code that could not be made) never show as errors. The bar dot uses the accent when ready, the urgent colour when the bridge is online but unpublished, and is hidden before Collie is installed.

## Widget settings

Settings live in the widget's `shell.json` layout entry:

| Setting | Default | Purpose |
| --- | --- | --- |
| `refreshIntervalSec` | `10` | Poll interval, clamped to 5–120 seconds |
| `collieBinary` | `collie` | Executable name or absolute path |
| `bridgePort` | `8787` | Local health probe and new-config port |

Executable lookup falls back to `~/.local/bin/collie` and `~/.local/share/collie/current/bin/collie`. Existing backend settings remain authoritative; set `bridgePort` to match an existing custom port. Named Collie instances are outside this widget's scope. With Powerbar, `powerbarVisibility: "shown"` keeps the widget visible.

## Development and verification

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v
python3 scripts/control.py status
python3 scripts/control.py doctor
omabox run --net isolated -- python3 tests/verify_ui.py
./demo/run ready
```

Run native previews inside omabox. The preview is a separate Quickshell instance in that private desktop with simulated service and installation actions. It never changes your real Collie installation. Scenarios: `missing`, `ready`, `no-qr`, `offline`, and `error`. The ready scenario covers repeated opening, close during pairing, settings changes during pairing, and vertical presentation. Close the preview process to remove its temporary files.

See [UX verification](docs/ux-verification.md) for the requirements-to-connectivity checks, research rationale, and the physical-phone check that remains manual.

Service commands use argument arrays without a shell. Health checks use a fixed loopback endpoint. The official 1.16.2 release archive is downloaded over HTTPS with a 256 MiB limit and a deadline, verified against `scripts/release.json`, and extracted with regular-file/path/count/expanded-size checks. No downloaded installer script executes. Collie's CLI owns service supervision, authentication, pairing, and proxy ownership.

IPC on `overp0werj0int.collie`: `open`, `close`, `toggle`, `refresh`, `status`, `setup` (the guided flow), `start`, `stop`, `restart`, `openBrowser` (open on this computer), `copyUrl`, `pairDevice` (Full control with a new code), `publish`, `diagnostics`. `status` includes the current message and the chosen way in, never the pairing code.

```bash
omarchy-shell overp0werj0int.collie open
omarchy-shell overp0werj0int.collie status
```

This is an independent MIT-licensed widget. Collie and Herdr are their respective projects; no upstream logo or application code is bundled.

## Update and removal

```bash
omarchy plugin update overp0werj0int.collie
omarchy plugin remove overp0werj0int.collie
```

Removing the widget removes its shell UI; it preserves Collie's installation, user service,
Tailscale route, backend configuration and paired devices. Stop the bridge before removal
if you want remote access paused. Use Collie's own CLI for backend updates and removal.

Project-local `.claude/skills` are authoring tools, ignored by Git and excluded from archives.
They are not part of the installed plugin. A manual directory copy should omit `.claude`,
`.agents`, `.codex` and `.aws`.

## Support and security reporting

Report widget bugs at https://github.com/overp0werj0int/omarchy-collie/issues.
Do not include pairing codes, QR images or credentials in reports. For sensitive findings,
use GitHub private vulnerability reporting if enabled; otherwise contact the owner privately
before sharing exploit details. Backend authentication and network security remain Collie's
and Tailscale's responsibility.

The automatic backend install pins Collie 1.16.2; reviewing a newer release requires updating
`scripts/release.json` and its evidence. Existing installations are reused and are not upgraded.
Linux x86-64 extraction was checked against the official archive; ARM64 has a pinned upstream
checksum but was not executed or tested on ARM hardware. Downloads are staged privately and
unrelated install paths are preserved. A failure after reserving the install directory may leave
that partial directory for explicit recovery; the widget never deletes it automatically.

Commands have separate 1 MiB stdout/stderr budgets and absolute deadlines. Mutating backend
operations serialize through a private runtime lock across widget instances. Pairing data remains
only in transient UI memory and is cleared on close, expiry, settings or connection changes;
showing the manual code requires an explicit button. Diagnostics are external CLI output;
review it before sharing. A custom `collieBinary` is executable code you choose to trust.

On several monitors each visual widget retains its own popup and transient pairing state.
Only the first active widget registers the public IPC target; ownership transfers when it is
removed. IPC backend actions are limited to one per second per owner. All visual instances
share the backend mutation lock, while status polling stays per monitor for compatibility with
replacement bars that do not expose hosted third-party services. This is not a shared-service
implementation; physical multi-monitor behavior remains a separate verification scope.
