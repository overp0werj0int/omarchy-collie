#!/usr/bin/env python3
"""Isolated, deterministic UX fixtures. Never install packages or modify a real service."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

spec = importlib.util.spec_from_file_location("helper", os.environ["COLLIE_LAB_HELPER"])
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
path = Path(os.environ["COLLIE_LAB_FIXTURE"])
scenario = os.environ.get("COLLIE_LAB_SCENARIO", "missing")
available = scenario in ("ready", "no-qr", "error", "offline")
ready = scenario in ("ready", "no-qr")
state = json.loads(path.read_text()) if path.exists() else {
    "installed": ready or scenario == "offline", "healthy": ready,
    "serviceState": "active" if ready else "inactive", "version": "demo" if ready or scenario == "offline" else "",
    "url": "https://collie-demo.example.ts.net", "tailnetPublished": ready,
    "tailscaleInstalled": available, "tailscaleReady": available,
    "muxes": ["herdr", "tmux"] if available else [], "qrAvailable": scenario != "no-qr" and ready,
    "missingTools": [] if available else ["curl"], "error": ""
}
if not path.exists() and scenario == "ready":
    state = json.loads((Path(os.environ["COLLIE_LAB_HELPER"]).parents[1] / "demo/fixtures/ready.json").read_text())
action = sys.argv[1]
name = sys.argv[sys.argv.index("--name") + 1] if "--name" in sys.argv else ""
state.setdefault("pairedDevices", 1)
answer = {"ok": True, "message": "Demo action complete."}
if action == "status":
    answer = state
elif action == "setup":
    for step, label in enumerate(("Checking requirements…", "Downloading official release…", "Preparing configuration…", "Starting bridge…", "Verifying connectivity…")):
        c.emit({"event": "progress", "stage": step, "message": label})
        time.sleep(0.35)
        if scenario == "error" and step == 1:
            c.emit({"ok": False, "message": "Download failed: network unavailable. Reconnect and retry."})
            sys.exit(1)
    state.update(installed=True, healthy=True, serviceState="active", tailnetPublished=True)
    answer.update(state=state, message="Backend ready. Open Phone to connect your device.")
elif action == "tailscale-setup":
    state.update(tailscaleInstalled=True, tailscaleReady=True)
elif action == "install-deps":
    time.sleep(.3)
    state.update(tailscaleInstalled=True, qrAvailable=True, missingTools=[])
    state["muxes"] = state["muxes"] or ["herdr"]
    answer["message"] = "Installed demo requirements."
elif action == "install-mux":
    state["muxes"] = ["herdr"]
elif action == "install-tools":
    state["missingTools"] = []
elif action == "install-qr":
    state["qrAvailable"] = True
elif action == "qr":
    answer.update(url=state["url"], qr=c.qr_image(state["url"]))
elif action == "pair":
    time.sleep(.25) # expose close/settings races deterministically
    url = c.pair_url(state["url"], "DEMO-ONLY", c.device_name(name))
    answer.update(pairCode="DEMO-ONLY", pairUrl=url, expiresAt=time.time()+600,
                  qr=c.qr_image(url), message="Demo pairing code. Scan to open Settings with the code filled in.")
elif action == "pair-qr":
    answer = {"ok": True, "qr": c.qr_image(c.pair_url(state["url"], os.environ["COLLIE_LAB_PAIR_CODE"], c.device_name(name)))}
elif action == "open":
    answer["message"] = "Opened Collie on this computer (demo: nothing was launched)."
elif action == "stop":
    state.update(healthy=False, serviceState="inactive")
elif action in ("start", "restart"):
    state.update(healthy=True, serviceState="active")
elif action == "serve":
    state["tailnetPublished"] = True
elif action == "doctor":
    answer["message"] = "Demo diagnostics: bridge healthy; tailnet route configured; requirements available."
# Atomic, so concurrent fixture calls never read a half-written state.
temporary = path.with_suffix(f".{os.getpid()}.tmp")
temporary.write_text(json.dumps(state))
temporary.replace(path)
c.emit(answer)
