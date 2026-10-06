# Collie Lab UX verification

Verified on 2026-10-04 with Omarchy Quattro / Quickshell and Collie 1.16.2. The flow is requirements → backend installation → configuration → service startup → private routing → phone opening → device pairing.

## Why this flow

The UI combines discovery and prerequisite checks from [Home Assistant config flows](https://developers.home-assistant.io/docs/core/integration/config_flow/) with the explicit [Docker Extensions Install → Open flow](https://docs.docker.com/extensions/marketplace/). A single contextual setup action coordinates the backend; it never runs during discovery or polling.

Named, real stages follow [Carbon's progress-indicator guidance](https://www.carbondesignsystem.com/building-blocks/core/components/progress-indicator/guidelines). The UI shows elapsed time, reports the failed stage, brings the error into view, and offers retry with details. It does not invent percentage completion or download progress.

Installation, service management, and pairing follow [Collie's official installation guide](https://colliepwa.dev/install). QR pairing opens `settings?pair=…`, following Collie's own CLI protocol. HTTPS and private routing follow [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).

## Verification results

| Journey / requirement | Verification | Result |
| --- | --- | --- |
| Widget package and entry point | `omarchy plugin validate .` | Passed |
| Missing Tailscale | Native `missing` fixture shows install/connect action | Passed |
| Missing workspace backend | Native fixture shows Install Herdr; unavailable choices disabled | Passed |
| Missing download tools | Inline install action; deployment disabled until requirements pass | Passed |
| No automatic installation | Polling only requests status and local QR generation; setup requires explicit action | Passed |
| Clean install orchestration | Temporary HOME; downloaded installer replaced with a local fixture, executed through a real subprocess | Passed |
| Download failure | Backend tests stop before configuration/start; native error fixture identifies install stage and enables retry | Passed |
| Missing custom executable | Setup reports settings error and does not install a replacement | Passed |
| Existing configuration | Tests preserve `.env`, instance TOML, and home TOML byte for byte | Passed |
| Fresh configuration permissions | Creates mode 0600 `.env`, loopback bind, selected backend, port, and detected trusted identity | Passed |
| Setup retry | Reuses installed executable and existing config | Passed |
| Duplicate setup | Runtime lock rejects concurrent install | Passed |
| Real existing-backend deployment | Official CLI start followed by health and Serve mapping checks | Passed |
| Offline bridge | Native fixture offers start; publishing remains a separate requirement | Passed |
| Readiness criteria | Tests require correct host, listener, mount, and loopback target; unrelated mappings do not count | Passed |
| Real HTTPS destination | Tailnet `/api/health` and `/` both return HTTP 200 with certificate verification enabled | Passed |
| Real rendered connection QR | Decoded the displayed native QR with `zbarimg`; matched the real `collie url` destination | Passed |
| Missing QR tool | Native `no-qr` fixture offers Install QR tool and updates after installation | Passed |
| Rendered pairing QR | Decoded native demo QR; matched Settings URL with prefilled code | Passed |
| Actual pairing claim | Temporary real Collie bridge with isolated config/state; one claim accepted, replay rejected with HTTP 400 | Passed |
| Pairing expiry | Native UI expiry clears code and QR regardless of subsequent actions | Passed |
| Pairing fallback | Backend tests preserve manual code when QR generation or URL lookup fails | Passed |
| Malformed output and timeout | Backend tests reject malformed readiness data and return structured action errors | Passed |
| Keyboard focus order | Native focus-chain checks include visible enabled controls and skip unavailable actions | Passed |
| Native runtime | Missing, no-QR, offline, and error fixtures load without QML scene warnings/errors | Passed |
| Physical phone connectivity | Phone sign-in, tailnet ACLs/DNS, camera scan, pairing confirmation, home-screen installation | Manual check required |

The backend suite has 22 tests. The UI scenario runner uses simulated package/service actions so it cannot install software, stop the real bridge, or alter production pairings. The real deployment smoke test reused the existing installation; it did not download and install another official release. The actual pairing claim used only a temporary bridge and deleted its state afterward.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
omarchy plugin validate .
python3 tests/verify_ui.py
bash tests/preview.sh missing
```

`verify_ui.py` requires Omarchy, `qs`, `qrencode`, and `zbarimg`. It opens isolated native previews, verifies requirement gating and transitions, and saves screenshots in a reported `/tmp/collie-lab-verification-*` folder. It closes each preview afterward. `preview.sh` provides interactive fixtures for `missing`, `ready`, `no-qr`, `offline`, and `error`. All actions there are simulated.

For the final physical check, enable Tailscale on a phone sharing this tailnet, scan the **Phone** tab's connection QR, confirm the Collie dashboard loads, generate and scan a pairing QR, confirm pairing in Settings, then install to the home screen. This is the remaining check that host-side tests cannot establish.
