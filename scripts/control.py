#!/usr/bin/env python3
"""Collie Lab: local status, official backend setup, and in-memory QR codes."""
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import ipaddress
import os
import platform
from pathlib import Path
import re
import selectors
import signal
import stat
import shutil
import subprocess
import sys
import tempfile
import tarfile
import time
import urllib.parse


OUTPUT_LIMIT = 1024 * 1024
_active_child = None


def terminate_child(child):
    # The leader remains unreaped until its group has been killed, preventing PGID reuse.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()


def interrupted(signum, frame):
    if _active_child is not None:
        terminate_child(_active_child)
    raise SystemExit(128 + signum)


def run(argv, timeout=8, input_text=None, binary=False, output_limit=OUTPUT_LIMIT):
    """Bound each pipe during receipt and enforce a whole-command deadline."""
    global _active_child
    if input_text is not None:
        payload = input_text if isinstance(input_text, bytes) else input_text.encode()
        if len(payload) > 16384:
            raise RuntimeError("Command input exceeds the supported size.")
    else:
        payload = None
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                             start_new_session=True,
                             env={k: v for k, v in {**os.environ, "NO_COLOR": "1"}.items()
                                  if k not in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH")})
    _active_child = child
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for name in buffers:
                pipe = getattr(child, name)
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            if payload is not None:
                os.set_blocking(child.stdin.fileno(), False)
                selector.register(child.stdin, selectors.EVENT_WRITE, "stdin")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("Command timed out. Retry or run diagnostics.")
                for key, events in selector.select(min(remaining, .2)):
                    if key.data == "stdin":
                        try:
                            written = os.write(key.fd, payload[:4096])
                            payload = payload[written:]
                        except BrokenPipeError:
                            payload = b""
                        if not payload:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        continue
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if len(buffers[key.data]) + len(chunk) > output_limit:
                        raise RuntimeError("Command output exceeded the safety limit. Run diagnostics separately.")
                    buffers[key.data].extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Command timed out. Retry or run diagnostics.")
            # Do not reap the leader before cleaning its process group.
            while True:
                info = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if info is not None:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("Command timed out. Retry or run diagnostics.")
                time.sleep(.01)
            terminate_child(child)
        values = [bytes(buffers[name]) for name in ("stdout", "stderr")]
        if not binary:
            values = [value.decode(errors="replace") for value in values]
        return subprocess.CompletedProcess(argv, child.returncode, *values)
    finally:
        if child.returncode is None:
            terminate_child(child)
        for pipe in (child.stdout, child.stderr, child.stdin):
            if pipe is not None and not pipe.closed:
                pipe.close()
        _active_child = None


def executable(requested):
    if not requested or requested.startswith("-"):
        return None
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
    result = run([binary, "url", "--plain"])
    # The CLI appends a note to its loopback fallback when Tailscale is down.
    lines = clean(result.stdout).splitlines()
    value = lines[0].split()[0] if lines else ""
    parts = urllib.parse.urlsplit(value)
    if result.returncode or parts.scheme not in ("http", "https") or not parts.hostname:
        raise RuntimeError(clean(result.stderr) or "Collie did not return a web URL.")
    if parts.username or parts.password or any(c.isspace() for c in value):
        raise RuntimeError("Collie returned an invalid web URL.")
    if len(value) > 4096 or parts.query or parts.fragment or any(ord(c) < 32 for c in value):
        raise RuntimeError("Collie returned an invalid web URL.")
    try:
        parts.port
    except ValueError:
        raise RuntimeError("Collie returned an invalid web URL.") from None
    return value


def phone_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme not in ("http", "https") or not host or parts.username or parts.password:
            return False
        if host == "localhost" or host.endswith(".localhost"):
            return False
        try:
            address = ipaddress.ip_address(host)
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if address.is_loopback or address.is_unspecified:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def prerequisites():
    state = {"tailscaleInstalled": bool(shutil.which("tailscale")), "tailscaleReady": False,
             "qrAvailable": bool(shutil.which("qrencode")), "muxes": [], "trustedUser": "",
             "missingTools": [tool for tool in ("curl",) if not shutil.which(tool)]}
    state["muxes"] = [name for name in ("herdr", "tmux", "zellij") if executable(name)]
    if state["tailscaleInstalled"]:
        try:
            result = run(["tailscale", "status", "--json"])
            data = json.loads(result.stdout) if result.returncode == 0 else {}
            if not isinstance(data, dict):
                data = {}
            state["tailscaleReady"] = data.get("BackendState") == "Running"
            self_data = data.get("Self")
            users = data.get("User")
            self_data = self_data if isinstance(self_data, dict) else {}
            users = users if isinstance(users, dict) else {}
            user = users.get(str(self_data.get("UserID", "")), {})
            login = user.get("LoginName", "") if isinstance(user, dict) else ""
            state["trustedUser"] = login if isinstance(login, str) else ""
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            pass
    return state


def mapping_published(config, url, port):
    """Match this URL's mount and this bridge, rather than any Serve listener."""
    parts = urllib.parse.urlsplit(url)
    try:
        listener = parts.port or (443 if parts.scheme == "https" else 80)
        web = config.get("Web", {}).get(f"{parts.hostname}:{listener}", {})
        target = web.get("Handlers", {}).get(parts.path or "/", {}).get("Proxy", "")
        parsed = urllib.parse.urlsplit(target)
        return parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == port
    except (AttributeError, TypeError, ValueError):
        return False


def status(binary, port):
    state = {"installed": bool(binary), "serviceState": "unknown", "healthy": False,
             "version": "", "url": "", "tailnetPublished": False, "error": "",
             "pairedDevices": -1, "thisComputerPaired": False, "devices": [],
             **prerequisites()}
    # Identity is only needed while seeding a new config, not in UI or IPC snapshots.
    state.pop("trustedUser", None)
    if not binary:
        return state
    try:
        service = run(["systemctl", "--user", "show", "collie.service",
                       "--property=ActiveState", "--value"])
        state["serviceState"] = service.stdout.strip()[:64] or "unknown"
        if service.returncode:
            state["error"] = clean(service.stderr)[:500]
        # Fixed loopback target, never a remote request or a session read.
        try:
            response = run(["/usr/bin/curl", "--disable", "--fail", "--silent", "--show-error",
                            "--noproxy", "*", "--max-time", "2", "--max-filesize", "16384",
                            f"http://127.0.0.1:{port}/api/health"], timeout=3, output_limit=16384)
            health = json.loads(response.stdout) if response.returncode == 0 else {}
            if isinstance(health, dict):
                state["healthy"] = health.get("ok") is True and health.get("deposed") is False
                state["version"] = str(health.get("version", ""))[:128]
        except (OSError, ValueError, RuntimeError):
            pass
        state["url"] = app_url(binary)
        try:
            devices = paired_devices(binary)
            mine = this_computer(devices, read_local(), this_host())
            state["pairedDevices"] = len(devices)
            state["thisComputerPaired"] = bool(mine)
            state["devices"] = [{"label": d[0][:48], "created": d[1], "lastSeen": d[2] if len(d) > 2 else None,
                                 "thisComputer": d[0] == mine} for d in devices[:50]]
        except (OSError, ValueError, RuntimeError):
            pass
        serve = run(["tailscale", "serve", "status", "--json"])
        if serve.returncode == 0:
            state["tailnetPublished"] = mapping_published(json.loads(serve.stdout), state["url"], port)
        else:
            state["error"] = clean(serve.stderr)[:500]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        state["error"] = str(error)[:500]
    return state


def qr_image(url):
    if not phone_url(url):
        raise RuntimeError("Connect Tailscale to generate a URL your phone can reach.")
    if not shutil.which("qrencode"):
        raise RuntimeError("Install the QR tool to display a scannable code.")
    # Rasterize modules at integer pixel sizes; Qt's SVG antialiasing creates seams.
    result = run(["qrencode", "-t", "PNG", "-l", "M", "-m", "4", "-s", "8", "-o", "-"],
                 input_text=url.encode(), binary=True)
    if result.returncode:
        raise RuntimeError(clean(result.stderr.decode(errors="replace")) or "Could not generate QR code.")
    return "data:image/png;base64," + base64.b64encode(result.stdout).decode()


def emit(answer):
    print(json.dumps(answer, ensure_ascii=False), flush=True)


def stage(number, message):
    emit({"event": "progress", "stage": number, "message": message})


def config_directory(binary):
    # Ask Collie for its resolved instance path, never guess over an existing config.
    result = run([binary, "config", "show", "--json", "--source", "default", "--plain"])
    if result.returncode == 0:
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or not isinstance(data.get("files", []), list):
            raise RuntimeError("Collie returned malformed configuration paths.")
        for entry in data.get("files", []):
            if isinstance(entry, dict) and entry.get("layer") == "instance":
                path = entry.get("path")
                if not isinstance(path, str) or not Path(path).is_absolute():
                    raise RuntimeError("Collie returned an invalid configuration path.")
                return Path(path).parent
    if executable("herdr"):
        result = run([executable("herdr"), "plugin", "config-dir", "herdr.collie"])
        path = clean(result.stdout)
        if result.returncode == 0 and path.startswith("/"):
            return Path(path)
    return Path.home() / ".config/collie"


def seed_config(binary, mux, port, login):
    directory = config_directory(binary)
    path = directory / ".env"
    # Preserve all existing .env / TOML choices. Setup is safe to retry.
    if path.exists() or (directory / "config.toml").exists() or (Path.home() / ".collie/config.toml").exists():
        return
    if not login or not re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", login):
        raise RuntimeError("Could not identify your Tailscale login. Connect Tailscale and retry.")
    dir_fd = private_directory(directory)
    try:
        fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)
    with os.fdopen(fd, "w") as stream:
        stream.write(f"COLLIE_MUX={mux}\nCOLLIE_HOST=127.0.0.1\nCOLLIE_PORT={port}\n"
                     f"COLLIE_TRUSTED_USER={login}\n")


def private_directory(path):
    """Traverse without following symlinks; retain the directory descriptor for writes."""
    path = Path(path)
    if not path.is_absolute():
        raise RuntimeError("Configuration and runtime directories must be absolute.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in (".", ".."):
                raise RuntimeError("Invalid configuration path.")
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise RuntimeError("Configuration directory must be owned by you and not writable by others.")
        return fd
    except BaseException:
        os.close(fd)
        raise


def locked_operation(callback):
    lock_dir = Path(os.environ.get("XDG_RUNTIME_DIR", str(Path.home() / ".cache"))) / "collie-lab"
    directory = private_directory(lock_dir)
    try:
        fd = os.open("setup.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(fd, "r+") as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("The operation lock must be a regular file owned by you.")
        if info.st_mode & 0o077:
            # Earlier versions left it readable; inside this private directory, tighten it in place.
            os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Backend setup is already running, or another action is in progress. Wait for it to finish.")
        return callback()


def setup(requested, port, mux):
    return locked_operation(lambda: deploy(requested, port, mux))


def extract_release(archive, folder, prefix):
    """Only bounded regular files and directories within one expected release root."""
    with tarfile.open(archive, "r:gz") as release:
        members = []
        expanded = 0
        names = set()
        for member in release:
            name = Path(member.name)
            if (name.is_absolute() or ".." in name.parts or not name.parts
                    or name.parts[0] != prefix or len(name.parts) > 32
                    or not (member.isfile() or member.isdir()) or member.name in names):
                raise RuntimeError("The release archive contains an unsafe entry.")
            expanded += member.size
            if len(members) >= 20000 or expanded > 512 * 1024 * 1024:
                raise RuntimeError("The release archive exceeds extraction limits.")
            names.add(member.name)
            members.append(member)
        release.extractall(folder, members=members, filter="data")
    binary = Path(folder) / prefix / "bin/collie"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("The verified release does not contain an executable Collie binary.")
    return binary.parent.parent


def release_metadata():
    return json.loads(Path(__file__).with_name("release.json").read_text())


def install_release():
    metadata = release_metadata()
    version = metadata["version"]
    arch = {"x86_64": "x64", "aarch64": "arm64"}.get(platform.machine())
    if platform.system() != "Linux" or not arch:
        raise RuntimeError("Automatic installation supports Linux x86-64 and ARM64 only.")
    platform_id = "linux-" + arch
    prefix = f"collie-{version}-{platform_id}"
    filename = prefix + ".tar.gz"
    url = f"https://github.com/{metadata['repository']}/releases/download/v{version}/{filename}"
    destination = Path.home() / ".local/share/collie"
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("A Collie directory already exists. Preserve it and use Collie's installer or update CLI to recover.")
    parent = private_directory(destination.parent)
    try:
        with tempfile.TemporaryDirectory(prefix="collie-release-", dir=destination.parent) as folder:
            archive = Path(folder) / filename
            result = run(["/usr/bin/curl", "--disable", "--fail", "--silent", "--show-error", "--location",
                          "--proto", "=https", "--proto-redir", "=https", "--max-time", "120",
                          "--max-filesize", "268435456", "--output", str(archive), url], timeout=125)
            if result.returncode:
                raise RuntimeError("Release download failed. Check connectivity and retry.")
            if archive.stat().st_size > 268435456:
                raise RuntimeError("Release download exceeds the size limit.")
            with archive.open("rb") as payload:
                actual = hashlib.file_digest(payload, "sha256").hexdigest()
            if actual != metadata["platforms"][platform_id]:
                raise RuntimeError("Release checksum mismatch. Nothing was installed.")
            payload = extract_release(archive, folder, prefix)
            # Reserve exclusively: never overwrite an existing install, including an unrelated directory.
            os.mkdir("collie", mode=0o700, dir_fd=parent)
            installed = os.open("collie", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                os.mkdir("versions", mode=0o700, dir_fd=installed)
                versions = os.open("versions", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=installed)
                try:
                    os.rename(payload, version, dst_dir_fd=versions)
                finally:
                    os.close(versions)
                os.symlink("versions/" + version, "current", dir_fd=installed)
            finally:
                os.close(installed)
        # The verified owning CLI publishes its launcher and preserves unrelated names.
        linked = run([str(destination / "current/bin/collie"), "link"], timeout=30)
        if linked.returncode:
            raise RuntimeError("Release installed, but Collie's launcher could not be linked. Run collie link from the installed binary.")
    finally:
        os.close(parent)


def deploy(requested, port, mux):
    stage(0, "Checking this machine…")
    checks = prerequisites()
    if not checks["tailscaleReady"]:
        raise RuntimeError("Connect this computer to Tailscale, then retry setup.")
    binary = executable(requested)
    if not binary and requested != "collie":
        raise RuntimeError("The custom Collie executable is missing. Correct it in widget settings.")
    if mux not in checks["muxes"]:
        raise RuntimeError(f"Install {mux} before setting up the bridge.")
    if not binary:
        for tool in ("curl",):
            if not shutil.which(tool):
                raise RuntimeError(f"The official installer needs {tool}. Install it and retry.")
        stage(1, "Downloading and verifying the reviewed Collie release…")
        install_release()
        binary = executable(requested)
        if not binary:
            raise RuntimeError("Installer finished but the Collie executable could not be found.")
    stage(2, "Preparing your backend configuration…")
    seed_config(binary, mux, port, checks["trustedUser"])
    stage(3, "Starting the bridge and publishing tailnet access…")
    result = run([binary, "start", "--plain"], timeout=120)
    if result.returncode:
        raise RuntimeError(clean(result.stdout + "\n" + result.stderr)[-4000:] or "Collie start failed.")
    stage(4, "Checking bridge health and the tailnet route…")
    snapshot = status(binary, port)
    for _ in range(4):
        if snapshot["healthy"]:
            break
        time.sleep(1)
        snapshot = status(binary, port)
    if not snapshot["healthy"] or not snapshot["tailnetPublished"]:
        return {"ok": False, "state": snapshot, "message":
                "Setup needs attention: " + ("the bridge is not answering. Run diagnostics."
                if not snapshot["healthy"] else "the tailnet route is missing. Enable HTTPS in Tailscale, then publish access.")}
    return {"ok": True, "state": snapshot, "message": "Backend ready. Open Phone to connect your device."}


CODE_PATTERN = r"[A-Za-z0-9_-]{4,128}"
DEVICE_LINE = re.compile(r"^(.+?)\s+created (\S+)\s+last seen (\S+)\s*$")


def device_name(raw):
    """Collie's own label rule: one line, at most 48 characters."""
    name = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", raw or "")).strip()
    return name[:48].strip()


def pair_url(base, code, name=""):
    # Collie's Settings fills the code from `pair`; `name` rides along for the device name.
    query = {"pair": code, **({"name": name} if name else {})}
    return base.rstrip("/") + "/settings?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote)


def timestamp(text):
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def mint_code(binary):
    result = run([binary, "pair", "--plain"], timeout=60)
    if result.returncode:
        # Even failed CLI output may contain a valid code: never copy it into general feedback.
        raise RuntimeError("Pairing failed. Make a new code or run Collie diagnostics.")
    lines = clean(result.stdout).splitlines()
    code = lines[0].strip() if lines else ""
    if not re.fullmatch(CODE_PATTERN, code):
        raise RuntimeError("Collie did not return a valid pairing code. Generate a new one.")
    expiry = re.search(r"expires (\S+)", clean(result.stdout + "\n" + result.stderr))
    return code, (timestamp(expiry[1]) if expiry else None) or time.time() + 600


def paired_devices(binary):
    result = run([binary, "devices", "list", "--plain"])
    if result.returncode:
        raise RuntimeError("Could not list Collie's paired devices.")
    devices = []
    for line in clean(result.stdout).splitlines():
        match = DEVICE_LINE.match(line)
        if match:
            # (label, created, last seen); a device never seen since pairing has no last-seen time.
            devices.append((match[1].strip(), timestamp(match[2]), timestamp(match[3])))
    return devices


def this_host():
    return device_name(platform.node().split(".")[0]) or "This computer"


def local_directory():
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "collie-lab"


def read_local():
    try:
        data = json.loads((local_directory() / "this-computer.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_local(data):
    directory = private_directory(local_directory())
    try:
        name = f".this-computer.{os.getpid()}.tmp"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
        os.replace(name, "this-computer.json", src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        os.close(directory)


def this_computer(devices, data, host):
    """The label this computer's browser was paired under, if it still holds one."""
    labels = [device[0] for device in devices]
    if data.get("label") in labels:
        return data["label"]
    start, end = data.get("mintedAt"), data.get("until")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        # A device enrolled while only the open-here code was pending is this browser.
        for label, created, *_ in devices:
            if created is not None and start - 5 <= created <= end + 5:
                return label
    return next((label for label in labels if label.casefold() == host.casefold()), None)


def launch_webapp(url):
    launcher = shutil.which("omarchy-launch-webapp")
    subprocess.Popen([launcher, url] if launcher else ["xdg-open", url], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def open_here(binary):
    """Collie in its own window with full control: pair this computer once, then go straight in."""
    base = app_url(binary)
    devices = paired_devices(binary)
    data = read_local()
    host = this_host()
    label = this_computer(devices, data, host)
    # With nothing paired Collie gates no writes, and pairing here would lock every other device out.
    if not devices or label:
        if label and data.get("label") != label:
            write_local({"label": label})
        launch_webapp(base)
        return {"ok": True, "message": "Opened Collie on this computer."}
    code, expires_at = mint_code(binary)
    write_local({"mintedAt": time.time(), "until": expires_at})
    launch_webapp(pair_url(base, code, host))
    return {"ok": True, "message": "Collie opened with the code filled in. Press Pair to finish."}


def revoke(binary, label):
    """Revoke one paired device by its exact label, as listed."""
    devices = paired_devices(binary)
    if label not in [device[0] for device in devices]:
        raise RuntimeError("That device is no longer paired.")
    if label.startswith("-"):
        raise RuntimeError(f"Revoke it in a terminal: collie devices revoke '{label}'")
    result = run([binary, "devices", "revoke", label, "--plain"], timeout=30)
    if result.returncode:
        raise RuntimeError(clean(result.stderr or result.stdout)[:500] or "Collie could not revoke that device.")
    if read_local().get("label") == label:
        write_local({})
    left = len(devices) - 1
    return {"ok": True, "message": f"Revoked {label}." + ("" if left else
            " No device is paired now, so Collie no longer asks devices to pair.")}


def action(binary, name, device=""):
    if not binary:
        raise RuntimeError("Collie executable was not found.")
    if name == "pair":
        code, expires_at = mint_code(binary)
        data = read_local()
        if isinstance(data.get("until"), (int, float)) and data["until"] > time.time():
            # This code replaces the open-here one: later devices are not this computer.
            data["until"] = time.time()
            write_local(data)
        answer = {"ok": True, "message": "Scan to open Collie with your pairing code filled in.",
                  "pairCode": code, "expiresAt": expires_at, "pairUrl": "", "qr": ""}
        try:
            answer["pairUrl"] = pair_url(app_url(binary), code, device_name(device))
            answer["qr"] = qr_image(answer["pairUrl"])
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            answer["message"] = str(error) + " Enter the code in Collie’s Settings → Paired devices."
        return answer
    if name == "pair-qr":
        # A renamed device keeps its code: the code arrives in the environment, never on argv.
        code = os.environ.get("COLLIE_LAB_PAIR_CODE", "")
        if not re.fullmatch(CODE_PATTERN, code):
            raise RuntimeError("No pairing code to draw. Make a new code.")
        return {"ok": True, "qr": qr_image(pair_url(app_url(binary), code, device_name(device)))}
    if name in ("start", "stop", "restart", "serve", "doctor"):
        result = run([binary, name, "--plain"], timeout=60)
        output = clean(result.stdout + "\n" + result.stderr)
        return {"ok": result.returncode == 0, "message": output[:6000] or f"{name} finished."}
    if name == "open":
        return open_here(binary)
    if name == "revoke":
        return revoke(binary, device)
    url = app_url(binary)
    if name == "copy":
        result = run(["wl-copy", "--type", "text/plain"], input_text=url)
        return {"ok": result.returncode == 0,
                "message": "Tailnet URL copied." if result.returncode == 0 else clean(result.stderr)}
    if name == "qr":
        return {"ok": True, "url": url, "qr": qr_image(url)}
    raise RuntimeError("Unsupported action.")


def needed_packages(binary, mux):
    """Everything a fresh setup still lacks, so one authorization prompt covers it all."""
    checks = prerequisites()
    packages = [] if checks["tailscaleInstalled"] else ["tailscale"]
    if not binary:
        if not checks["muxes"]:
            packages.append(mux)
        if not checks["qrAvailable"]:
            packages.append("qrencode")
        packages += checks["missingTools"]
    return packages


def install_requirement(name, mux, binary=None):
    if name == "install-deps":
        packages = needed_packages(binary, mux)
        if not packages:
            return {"ok": True, "message": "Requirements are already installed."}
    else:
        packages = {"install-qr": ["qrencode"], "install-mux": [mux],
                    "install-tools": ["curl", "tar", "coreutils"]}[name]
    result = run(["/usr/bin/pkexec", "/usr/bin/pacman", "-S", "--needed", "--noconfirm", *packages], timeout=300)
    return {"ok": result.returncode == 0,
            "message": "Installed " + ", ".join(packages) + "." if result.returncode == 0
            else clean(result.stderr) or "Installation was cancelled. Retry to continue."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "setup", "install-deps", "install-qr", "install-mux", "install-tools", "tailscale-setup", "start", "stop", "restart", "serve", "open", "copy", "qr", "pair", "pair-qr", "revoke", "doctor"))
    parser.add_argument("--binary", default="collie")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--mux", choices=("herdr", "tmux", "zellij"), default="herdr")
    parser.add_argument("--name", default="", help="device name carried by a pairing link")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    binary = executable(args.binary)
    try:
        if args.action == "setup":
            answer = setup(args.binary, args.port, args.mux)
        elif args.action in ("install-deps", "install-qr", "install-mux", "install-tools"):
            answer = locked_operation(lambda: install_requirement(args.action, args.mux, binary))
        elif args.action == "tailscale-setup":
            subprocess.Popen(["omarchy", "launch", "terminal", "bash", str(Path(__file__).with_name("tailscale-setup.sh"))],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            answer = {"ok": True, "message": "Finish signing in to Tailscale in the terminal."}
        else:
            if args.action == "status":
                answer = status(binary, args.port)
            elif args.action in ("start", "stop", "restart", "serve", "pair", "open", "revoke"):
                answer = locked_operation(lambda: action(binary, args.action, args.name))
            else:
                answer = action(binary, args.action, args.name)
    except subprocess.TimeoutExpired:
        answer = {"ok": False, "message": "Command timed out. Retry or run diagnostics."}
    except (OSError, ValueError, RuntimeError) as error:
        answer = {"ok": False, "message": str(error)[:6000]}
    emit(answer)
    return 0 if answer.get("ok", True) else 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    sys.exit(main())
