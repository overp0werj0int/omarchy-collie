# Collie plugin review — 6 October 2026

The review fixed the actionable findings below. The reviewed runtime passed 38 backend/security
regression tests, five native UX scenarios, hosted IPC on two virtual outputs, a writable Git
update/removal fixture, official validation and a payload-only static release preflight.
This is scoped review and test evidence, not a security certification or marketplace approval.

## Source and scope

- Workspace: `omarchy-collie`, manifest version 1.1.0.
- Original HEAD: `532d529b99e811efd2bd4f4e4e2d2b35c62ad6e9` with pre-existing changes.
  Those changes were preserved; the workspace was not committed, reset, or published.
- A temporary, clean payload snapshot used for release preflight: `84f9329930784fe6a4f08e983282ce069c423cc7`.
  This is a local review fixture, not a release commit or tag in the project repository.
- Native tests ran **in omabox**, on Omarchy 4.0.4-1, Hyprland 0.56.2, theme `waffle-cat`,
  initially 1920×1080 at scale 1. A second virtual output reproduced the IPC problem.
- The 12 project-local Omarchy skill packages were read and applied where relevant. The installed
  collection does not contain a separate UX or security skill. UX was evaluated using bar/panel,
  QML, demo and test guidance; security used reviewer-boundary guidance and manual source review.
- No real backend installation, package installation, pairing, service restart or desktop change
  was performed as part of this review. Tests used fictional data and private desktops.
  The new runtime has **not** been copied into the user's installed widget.

## Findings and fixes

| Finding | Priority | Fix | Evidence |
| --- | --- | --- | --- |
| Downloaded installer code was mutable and selected releases dynamically | High | Removed remote script execution. New installs fetch official Collie 1.16.2 archives and compare SHA-256 to `scripts/release.json` before extraction or execution | Mismatch refuses installation; real x86-64 archive hash and extraction checked |
| Download/extraction had no plugin-owned archive policy | High | HTTPS-only redirects; 256 MiB download cap and 120 s curl deadline; 512 MiB expansion, 20,000-entry and depth limits; only expected-root regular files/directories; no links or traversal | Malicious path, absolute path, link, duplicate and oversized-member tests |
| `subprocess.run(capture_output=True)` buffered arbitrary stdout/stderr | High | Selector-based reader enforces independent 1 MiB budgets while receiving, before JSON parsing or QML collection | Actual stdout/stderr overflow and unterminated slow-drip tests |
| A timed-out or cancelled helper could leave descendants alive | High | Children run in private process groups; cleanup kills the group and reaps the leader, retaining its identity until cleanup; SIGTERM/SIGINT cleanup hooks | Deadline, descendant and helper-cancellation tests |
| Timeout/failing pairing output could disclose a code in ordinary feedback | Medium | Generic timeout messages without captured output; unsuccessful pairing no longer echoes raw stdout/stderr | Partial-secret and failed-pairing tests |
| Config and operation-lock writes followed filesystem paths without a no-follow boundary | Medium | Descriptor-based component traversal, no-follow opens, exclusive 0600 config creation, ownership/write-permission checks and private regular-file lock validation | Symlink directory/lock rejection; existing config remains unchanged |
| Concurrent widget/IPC actions could mutate one backend simultaneously | Medium | Setup, install requirements, start/stop/restart, publish and pair share a non-blocking runtime lock; public IPC actions have a one-second per-owner limit | Lock contention test; state inspection |
| A health probe could follow a redirect away from its fixed loopback endpoint | Medium | Fixed loopback curl URL, no redirects/proxies/curlrc, 16 KiB budget and absolute transport/helper deadlines | Real local redirect server test observed only `/api/health` |
| Nested malformed Tailscale/config data could crash parsing | Medium | Type-check nested identity/maps and CLI config paths; bounded status fields; ANSI-only URL output handled | Malformed nested identity, mapping and URL tests; configuration-path source review |
| Ambiguous/credential-bearing URLs and loopback variants could reach QR generation | Medium | Reject URL credentials, query/fragment-bearing base URLs, invalid ports; classify loopback, unspecified and IPv4-mapped loopback addresses | Invalid/ambiguous URL and loopback variant tests |
| Late status/QR/pairing replies could overwrite a newer configuration | Medium | Requests carry a settings/revision identity; old replies are discarded; QR regeneration is rescheduled when invalidated | Native settings-change-during-pairing scenario |
| Pairing material survived popup closure; a reply could resurrect it | Medium | Clear transient code/image on close and settings change; invalidate pairing requests closed before completion; retain expiry/offline clearing | Close during pairing and completed-pair close tests |
| Read/write QR mode could be confusing or revert to a normal QR | Medium | Explicit connection/pairing selector; automatic embedded code; expiry stays in pairing mode; manual code hidden behind an explicit button; `Copy app URL` labels its actual payload | Native pairing QR decoded to fictional `settings?pair=DEMO-ONLY`; expiry/mode tests and screenshots |
| One IPC target was registered by every monitor widget | Medium | Shared `IpcOwner.js` elects one active visual owner and transfers ownership when removed | Reproduced duplicate warning before fix; no Collie duplicate warnings after shell restart on two outputs; native election/transfer probe |
| Executable/privilege lookup could depend on PATH shims | Medium | QML uses `/usr/bin/python3 -I`; fixed absolute curl, pkexec/pacman and sudo/systemctl/Tailscale paths for privileged setup; loader injection variables scrubbed in subprocess environment; curlrc disabled | Source inspection, real helper tests, fixed-package argv test |
| Development agent skills would be copied with a manually assembled plugin tree | Low | Keep requested local skills in `.claude/skills`; Git ignore plus archive exclusions; reviewed payload omits authoring directories | Payload scan contains no agent-configuration findings; whole-workspace scan separately identifies ignored skill content |
| Demo, release and support evidence was incomplete | Low | Added fictional fixture/demo runner, real native preview, pinned-action CI configuration, portable test runner, update/remove and support/security instructions | Demo preflight, official validation, payload preflight and writable Git lifecycle fixture |

## Skill coverage

| Skill | Application and outcome |
| --- | --- |
| omarchy-plugin-design | Reviewed permanent ID, entry points, state ownership, commands, credentials and installer boundaries. Preserved the existing one-widget architecture |
| omarchy-bar-widget | Checked manifest/settings, pointer actions, small displays, keyboard focus and vertical presentation; preserved hosted bar primitives |
| omarchy-panel-overlay | Checked open/repeated-open/close and stale completion after close; retained the native KeyboardPanel rather than introducing windows |
| omarchy-qml-patterns | Kept theme tokens, argument arrays and external text as plain text; isolated Python, bounded producers and guarded async state |
| omarchy-service-ipc | Fixed duplicate IPC ownership, limited public mutations and serialized cross-widget changes. Per-monitor status polling is retained for replacement-bar compatibility; no hosted service is claimed |
| omarchy-plugin-debug | Doctor and installed official validator passed. Hosted load, IPC and shell restart were checked in omabox |
| omarchy-plugin-demo | Fictional committed state and isolated runner added; native connection/pairing/vertical images captured. Static preflight passes with a fixture-only warning because it does not understand omabox isolation |
| omarchy-plugin-test | 38 backend/security tests and five native UX scenarios passed; two-output IPC and writable Git lifecycle checks passed |
| omarchy-plugin-migrate | Confirmed package/daemon/credentials remain owned by external CLIs. Installation is explicit, never a plugin-load hook; removal retains backend data |
| omarchy-plugin-scaffold | Applied missing test/CI/demo hygiene to the existing repository; did not regenerate it. Authoring skills stay local |
| omarchy-plugin-release | Clean temporary payload preflight passed without errors. Workspace remains dirty; no tag/release or release readiness claim |
| omarchy-plugin-publish | Reviewed root manifest, README, license, preview, dependency/removal disclosures. No issue or owner attestations created; current marketplace form was not revalidated |

## Commands and evidence

Executed:

```bash
omarchy plugin validate .
python3 .claude/skills/omarchy-plugin-debug/scripts/doctor.py .
python3 .claude/skills/omarchy-plugin-demo/scripts/demo_preflight.py .
omabox run -- ./tests/run
omabox run -- python3 tests/verify_ui.py
omabox run -- python3 tests/verify_lifecycle.py
```

The final UI run saved artifacts with `env COLLIE_LAB_ARTIFACTS=/home/sbx/collie-final-artifacts`
inside the existing box. The test runner also works with a throwaway box. The lifecycle fixture
refuses to run unless its HOME is `/home/sbx`; it uses a writable, renamed Git fixture and a retained
marker. It establishes clone/enable/disable/update/remove behavior in a private desktop, not a real
backend uninstall or an authenticated HTTPS `omarchy plugin add` installation.

A mounted development plugin is read-only in omabox. An initial removal probe correctly failed
on that mount; removal evidence comes from the subsequent writable Git fixture, not that failed probe.

On the final payload, `validate_plugin.py --json --security` reports a valid manifest and **zero
security findings**. Remaining capability warnings identify QML process/collector use, installers,
privilege tools and service management; those paths were manually reviewed above. A scan of the
whole workspace flags an unpinned-command *example inside the ignored authoring validator* and
agent configuration content. Neither is in the reviewed payload; the skill files were not modified
to conceal those warnings.

The payload release preflight passed. Its warnings are capability disclosures, not certification.
The temporary payload omits `.claude`, `.agents`, `.codex`, `.aws` and bytecode caches. A pinned CI
workflow was added from the skill's template; GitHub Actions has **not** been run for this dirty
workspace, and action provenance beyond the supplied template was not independently audited.

Native images:

- [Connection view](../preview.png)
- [Pairing view with fictional one-time code](review-evidence/pair-demo.png)
- [Vertical presentation fixture](review-evidence/vertical-demo.png)

## Limits and remaining checks

1. Physical phone scan, its Tailscale identity/ACLs/DNS, pairing confirmation and PWA installation
   remain manual. The backend's `pair` URL protocol still requires the phone's confirmation tap;
   there is no code typing, but this plugin does not bypass upstream confirmation.
2. Physical monitors, fractional scale, real input devices and physical multi-monitor behavior were
   not tested. The two-output test uses virtual screens. Existing shell warnings about unavailable
   hardware/session services and built-in duplicate handlers were distinguished from Collie warnings.
3. The x86-64 official release archive was downloaded, hashed and extracted (124 entries; 89,380,166
   expanded bytes). It was not installed into the real HOME or started against real services.
   ARM64 has the upstream release checksum pinned, but its binary and hardware were not tested.
4. Existing configured backend binaries are reused and remain user-selected executable code.
   The pinned new-install path is not proof that existing backend versions are safe. Authentication,
   request identity and backend vulnerability review are external to this widget's scope.
5. A checksum pin prevents subsequent remote drift; its initial provenance relies on the official
   GitHub release over HTTPS, not an independent signing/attestation system. New release pins require
   review. The plugin no longer automatically installs whichever release appears newest.
6. A failure after exclusively reserving a new install directory may leave it for explicit recovery.
   No partial/unrelated installation is recursively deleted automatically. Removing the shell widget
   intentionally preserves packages, Collie services, configuration, routes and paired devices.
7. Per-monitor polling remains bounded but is not a hosted singleton service. This preserves
   compatibility with replacement bars whose scoped facade cannot expose third-party services.
   No service-facade bypass was introduced.
8. Omakit and a full VM check were not run. Marketplace baseline, authenticated remote installation,
   owner attestations, source commit/tag alignment and public release/CI remain separate gates.
9. The user's installed widget retains its previous runtime. This review changes the project only;
   deploy the reviewed runtime separately if desired. Private test desktops were torn down.

## Runtime identity

These hashes bind the final tested runtime independently of the pre-existing dirty workspace:

```json
{
  "ColliePanel.qml": "dbe0d3e6921da34a6c2ed5178e33688da1d715ddeaa079b093b852f3562713d7",
  "IpcOwner.js": "28dcd6255f17dc14129c93b3eaf02fb96d8b6af9ce584e16d18dfd8a9690fc38",
  "manifest.json": "2f4231d9834c19ca3f8e6e8442d63ec70afa368b90c477833e10ce764f7063b9",
  "scripts/control.py": "d6a4b556d824cf9d4495f1e33e23c16c44176234a0c9dfc61eb155d87f44ffad",
  "scripts/release.json": "f164258e92ad79cb695e03319abe156f882777b9ecdbebd7e555a7a113168c8a",
  "scripts/tailscale-setup.sh": "4d0a9e0289184b4da963af684f8097ca14e45469eef18a486918e9928567e29b"
}
```

## Live deployment — 6 October 2026

After the review, the user explicitly requested deployment. The six runtime file hashes above
were verified against the project, copied to the installed plugin, and verified again.
Dependencies were deployed before the QML entry point using atomic file replacement.
Official installed-plugin validation passed. The live shell rediscovered the enabled widget,
and IPC status reported an active, healthy backend with no widget error.
The first refresh probe ran during hot reload and briefly returned “Target not found”;
the next probe succeeded without restarting the shell or backend.

Previous installed plugin backup: `/home/p0werj0int/.local/state/omarchy/collie-backups/deploy-20261006-144759-62c2daed/plugin`.

The earlier “not deployed” statements describe the state at completion of the review;
this deployment supersedes them. Phone-side checks remain manual.
