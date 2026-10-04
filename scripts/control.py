#!/usr/bin/env python3
"""Local, argv-only control of the official Collie CLI. No root or extra packages."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


def run(argv, timeout=8, input_text=None):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          input=input_text, env={**os.environ, "NO_COLOR": "1"})


def executable(requested):
    found = shutil.which(os.path.expanduser(requested))
    if found:
        return found
    if requested == "collie":
        for path in (Path.home() / ".local/bin/collie",
                     Path.home() / ".local/share/collie/current/bin/collie"):
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
    return None


def clean(text):
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).strip()


def app_url(binary):
    result = run([binary, "url"])
    value = result.stdout.strip()
    parts = urllib.parse.urlsplit(value)
    if result.returncode or parts.scheme not in ("http", "https") or not parts.hostname:
        raise RuntimeError(clean(result.stderr) or "Collie did not return a web URL.")
    if parts.username or parts.password or any(c.isspace() for c in value):
        raise RuntimeError("Collie returned an invalid web URL.")
    return value


def mapping_published(config, url, port):
    """Match this URL's mount and this bridge, rather than any Serve listener."""
    parts = urllib.parse.urlsplit(url)
    listener = parts.port or (443 if parts.scheme == "https" else 80)
    web = config.get("Web", {}).get(f"{parts.hostname}:{listener}", {})
    target = web.get("Handlers", {}).get(parts.path or "/", {}).get("Proxy", "")
    try:
        parsed = urllib.parse.urlsplit(target)
        return parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == port
    except ValueError:
        return False


def status(binary, port):
    state = {"installed": bool(binary), "serviceState": "unknown", "healthy": False,
             "version": "", "url": "", "tailnetPublished": False, "error": ""}
    if not binary:
        state["error"] = "Install Collie first; see the widget README."
        return state
    try:
        service = run(["systemctl", "--user", "show", "collie.service",
                       "--property=ActiveState", "--value"])
        state["serviceState"] = service.stdout.strip() or "unknown"
        if service.returncode:
            state["error"] = clean(service.stderr)[:500]
        # Fixed loopback target, never a remote request or a session read.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
                health = json.loads(response.read(16384))
            state["healthy"] = health.get("ok") is True and health.get("deposed") is False
            state["version"] = str(health.get("version", ""))
        except (OSError, ValueError):
            pass
        state["url"] = app_url(binary)
        serve = run(["tailscale", "serve", "status", "--json"])
        if serve.returncode == 0:
            state["tailnetPublished"] = mapping_published(json.loads(serve.stdout), state["url"], port)
        else:
            state["error"] = clean(serve.stderr)[:500]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        state["error"] = str(error)[:500]
    return state


def action(binary, name):
    if not binary:
        raise RuntimeError("Collie executable was not found.")
    if name in ("start", "stop", "restart", "serve", "pair", "doctor"):
        result = run([binary, name, "--plain"], timeout=60)
        output = clean(result.stdout + "\n" + result.stderr)
        if name == "pair" and result.returncode == 0:
            # Keep the code and expiry; terminal block QR does not fit a popup.
            code = result.stdout.splitlines()[0].strip()
            output = f"Pairing code: {code}\nValid for 10 minutes, once.\nOn your phone: Settings → Paired devices."
        return {"ok": result.returncode == 0, "message": output[:6000] or f"{name} finished."}
    url = app_url(binary)
    if name == "open":
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return {"ok": True, "message": "Opened Collie in your browser."}
    if name == "copy":
        result = run(["wl-copy", "--type", "text/plain"], input_text=url)
        return {"ok": result.returncode == 0,
                "message": "Tailnet URL copied." if result.returncode == 0 else clean(result.stderr)}
    raise RuntimeError("Unsupported action.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "start", "stop", "restart", "serve", "open", "copy", "pair", "doctor"))
    parser.add_argument("--binary", default="collie")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    binary = executable(args.binary)
    try:
        answer = status(binary, args.port) if args.action == "status" else action(binary, args.action)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        answer = {"ok": False, "message": str(error)}
    print(json.dumps(answer, ensure_ascii=False))
    return 0 if answer.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
