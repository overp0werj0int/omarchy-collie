"""Verify setup boundaries and the phone connection contract without modifying the host."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("control", Path(__file__).resolve().parents[1] / "scripts/control.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def result(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        # Pairing records which device is this computer: keep that out of the real home.
        self.state = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ, {"XDG_STATE_HOME": self.state.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.state.cleanup)

    def test_loopback_fallback_note_is_parsed_and_never_encoded(self):
        with patch.object(c, "run", return_value=result("http://127.0.0.1:8787 (Tailscale name unavailable)\n")):
            url = c.app_url("collie")
        self.assertEqual(url, "http://127.0.0.1:8787")
        with self.assertRaisesRegex(RuntimeError, "Connect Tailscale"):
            c.qr_image(url)

    def test_invalid_url_and_credentials_are_rejected(self):
        for url in ("file:///etc/passwd", "https://user:password@host.ts.net", "", "\x1b[31m", "javascript:alert(1)"):
            with self.subTest(url=url), patch.object(c, "run", return_value=result(url)):
                with self.assertRaises((RuntimeError, ValueError)):
                    c.app_url("collie")

    def test_tailnet_mapping_must_match_host_mount_listener_and_target(self):
        config = {"Web": {"host.ts.net:8443": {"Handlers": {"/collie/": {"Proxy": "http://127.0.0.1:9000"}}}}}
        self.assertTrue(c.mapping_published(config, "https://host.ts.net:8443/collie/", 9000))
        for url, port in (("https://host.ts.net/collie/", 9000), ("https://other.ts.net:8443/collie/", 9000),
                          ("https://host.ts.net:8443/", 9000), ("https://host.ts.net:8443/collie/", 8787)):
            self.assertFalse(c.mapping_published(config, url, port))

    def test_qr_is_local_png_with_quiet_zone_and_stdin_payload(self):
        with patch.object(c.shutil, "which", return_value="/usr/bin/qrencode"), patch.object(c, "run", return_value=result(b"PNG-image")) as run:
            encoded = c.qr_image("https://host.ts.net")
        self.assertEqual(base64.b64decode(encoded.split(",", 1)[1]), b"PNG-image")
        self.assertEqual(run.call_args.kwargs["input_text"], b"https://host.ts.net")
        self.assertIn("4", run.call_args.args[0])
        self.assertNotIn("https://host.ts.net", run.call_args.args[0])

    def test_pair_link_prefills_settings_and_honors_cli_expiry(self):
        output = "ABC123\n\n single-use · expires 2030-01-01T00:00:00Z (10 minutes)\n"
        with patch.object(c, "run", return_value=result(output)), patch.object(c, "app_url", return_value="https://host.ts.net/collie/"), patch.object(c, "qr_image", return_value="image"):
            answer = c.action("collie", "pair")
        self.assertEqual(answer["pairUrl"], "https://host.ts.net/collie/settings?pair=ABC123")
        self.assertEqual(answer["pairCode"], "ABC123")
        self.assertEqual(answer["expiresAt"], 1893456000)
        self.assertNotIn("ABC123", answer["message"])

    def test_pair_link_carries_a_clean_device_name(self):
        with patch.object(c, "run", return_value=result("ABC123\n")), patch.object(c, "app_url", return_value="https://host.ts.net/"), patch.object(c, "qr_image", return_value="image"):
            answer = c.action("collie", "pair", "  Ann's\niPad & co  ")
        self.assertEqual(answer["pairUrl"], "https://host.ts.net/settings?pair=ABC123&name=Ann%27s%20iPad%20%26%20co")
        self.assertEqual(len(c.device_name("x" * 80)), 48)
        self.assertEqual(c.pair_url("https://h.ts.net", "C0DE"), "https://h.ts.net/settings?pair=C0DE")

    def test_paired_devices_are_parsed_from_the_cli_list(self):
        listing = "Iphone       created 2026-10-04T20:14:43.511Z  last seen 2026-10-06T15:12:53.157Z\nWork laptop  created 2026-10-05T08:00:00Z  last seen never\n"
        with patch.object(c, "run", return_value=result(listing)):
            devices = c.paired_devices("collie")
        self.assertEqual([device[0] for device in devices], ["Iphone", "Work laptop"])
        self.assertAlmostEqual(devices[0][1], 1791144883.511, places=2)
        self.assertIsNone(devices[1][2]) # never seen
        with patch.object(c, "run", return_value=result("no devices paired — pairing is not enforced\n")):
            self.assertEqual(c.paired_devices("collie"), [])

    def test_open_here_goes_straight_in_when_nothing_gates_writes(self):
        with patch.object(c, "app_url", return_value="https://host.ts.net"), patch.object(c, "paired_devices", return_value=[]), patch.object(c, "mint_code") as mint, patch.object(c, "launch_webapp") as launch:
            self.assertTrue(c.open_here("collie")["ok"])
        mint.assert_not_called()
        launch.assert_called_once_with("https://host.ts.net")

    def test_open_here_pairs_this_computer_once(self):
        devices = [("Iphone", 100.0)]
        with patch.object(c, "app_url", return_value="https://host.ts.net"), patch.object(c, "paired_devices", side_effect=lambda binary: devices), patch.object(c, "this_host", return_value="legion"), patch.object(c, "mint_code", return_value=("K7P2XQ9M", 2e9)), patch.object(c, "launch_webapp") as launch, patch.object(c.time, "time", return_value=1000.0):
            c.open_here("collie")
            self.assertEqual(launch.call_args.args[0], "https://host.ts.net/settings?pair=K7P2XQ9M&name=legion")
            # Whatever name it was given in the window, the device enrolled in that window is this one.
            devices.append(("my desk", 1100.0))
            c.open_here("collie")
            self.assertEqual(launch.call_args.args[0], "https://host.ts.net")
            self.assertEqual(c.read_local(), {"label": "my desk"})

    def test_a_phone_code_ends_the_open_here_window(self):
        c.write_local({"mintedAt": 1000.0, "until": 1600.0})
        with patch.object(c, "run", return_value=result("ABC123\n")), patch.object(c, "app_url", side_effect=RuntimeError("offline")), patch.object(c.time, "time", return_value=1200.0):
            c.action("collie", "pair")
        self.assertEqual(c.read_local()["until"], 1200.0)
        # The phone enrolled after its own code is not mistaken for this computer.
        self.assertIsNone(c.this_computer([("Iphone", 1300.0)], c.read_local(), "legion"))
        self.assertEqual(c.this_computer([("LEGION", 50.0)], {}, "legion"), "LEGION")

    def test_revoke_runs_the_cli_for_a_listed_device_and_forgets_this_computer(self):
        c.write_local({"label": "legion"})
        with patch.object(c, "paired_devices", return_value=[("legion", 1.0, None), ("Iphone", 2.0, 3.0)]), patch.object(c, "run", return_value=result("revoked\n")) as run:
            answer = c.action("collie", "revoke", "legion")
        self.assertEqual(run.call_args.args[0], ["collie", "devices", "revoke", "legion", "--plain"])
        self.assertEqual(answer["message"], "Revoked legion.")
        self.assertEqual(c.read_local(), {})
        with patch.object(c, "paired_devices", return_value=[("Iphone", 2.0, 3.0)]), patch.object(c, "run", return_value=result()):
            self.assertIn("No device is paired", c.action("collie", "revoke", "Iphone")["message"])

    def test_revoke_refuses_unknown_or_option_like_labels(self):
        with patch.object(c, "paired_devices", return_value=[("-rf", 1.0, None)]), patch.object(c, "run") as run:
            for label in ("ghost", "-rf"):
                with self.subTest(label=label), self.assertRaises(RuntimeError):
                    c.action("collie", "revoke", label)
        run.assert_not_called()

    def test_pair_code_survives_missing_qr_tool(self):
        with patch.object(c, "run", return_value=result("ABC123\n")), patch.object(c, "app_url", return_value="https://host.ts.net"), patch.object(c, "qr_image", side_effect=RuntimeError("Install the QR tool.")):
            answer = c.action("collie", "pair")
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["pairCode"], "ABC123")
        self.assertEqual(answer["qr"], "")
        self.assertIn("Enter the code", answer["message"])

    def test_logged_out_tailscale_is_not_ready(self):
        with patch.object(c.shutil, "which", return_value="tool"), patch.object(c, "executable", return_value="tool"), patch.object(c, "run", return_value=result('{"BackendState":"NeedsLogin"}')):
            self.assertFalse(c.prerequisites()["tailscaleReady"])

    def test_malformed_status_is_not_reported_ready(self):
        for config in ([], {"Web": None}, {"Web": {"host.ts.net:443": []}}):
            self.assertFalse(c.mapping_published(config, "https://host.ts.net", 8787))
        with patch.object(c.shutil, "which", return_value="tool"), patch.object(c, "executable", return_value="tool"), patch.object(c, "run", return_value=result('[]')):
            self.assertFalse(c.prerequisites()["tailscaleReady"])

    def test_pair_code_survives_unavailable_url(self):
        with patch.object(c, "run", return_value=result("ABC123\n")), patch.object(c, "app_url", side_effect=RuntimeError("URL unavailable")):
            answer = c.action("collie", "pair")
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["pairCode"], "ABC123")
        self.assertEqual(answer["qr"], "")

    def test_empty_pair_result_is_actionable_error(self):
        with patch.object(c, "run", return_value=result("")):
            with self.assertRaisesRegex(RuntimeError, "valid pairing code"):
                c.action("collie", "pair")

    def test_cli_timeout_returns_structured_failure(self):
        with patch.object(c.sys, "argv", ["control.py", "restart"]), patch.object(c, "executable", return_value="collie"), patch.object(c, "locked_operation", side_effect=subprocess.TimeoutExpired("collie", 60)), contextlib.redirect_stdout(io.StringIO()) as output:
            exit_code = c.main()
        answer = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(answer["ok"])
        self.assertIn("timed out", answer["message"])


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home_patch = patch.object(c.Path, "home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.checks = {"tailscaleReady": True, "muxes": ["herdr"], "trustedUser": "you@example.com"}

    def test_new_configuration_is_private_and_uses_detected_identity(self):
        folder = self.home / "config"
        with patch.object(c, "config_directory", return_value=folder):
            c.seed_config("collie", "herdr", 9000, "you@example.com")
        data = (folder / ".env").read_text()
        self.assertIn("COLLIE_TRUSTED_USER=you@example.com", data)
        self.assertIn("COLLIE_HOST=127.0.0.1", data)
        self.assertIn("COLLIE_PORT=9000", data)
        self.assertEqual((folder / ".env").stat().st_mode & 0o777, 0o600)

    def test_existing_env_or_toml_is_never_replaced(self):
        for name in (".env", "config.toml"):
            folder = self.home / name.replace(".", "_")
            folder.mkdir()
            path = folder / name
            path.write_text("operator's own configuration\n")
            with patch.object(c, "config_directory", return_value=folder):
                c.seed_config("collie", "herdr", 9000, "")
            self.assertEqual(path.read_text(), "operator's own configuration\n")
            if name == "config.toml":
                self.assertFalse((folder / ".env").exists())

    def test_home_toml_is_preserved(self):
        (self.home / ".collie").mkdir()
        (self.home / ".collie/config.toml").write_text("# custom")
        with patch.object(c, "config_directory", return_value=self.home / "config"):
            c.seed_config("collie", "herdr", 9000, "")
        self.assertFalse((self.home / "config/.env").exists())

    def test_missing_identity_does_not_create_unrestricted_config(self):
        with patch.object(c, "config_directory", return_value=self.home / "config"):
            with self.assertRaisesRegex(RuntimeError, "Tailscale login"):
                c.seed_config("collie", "herdr", 8787, "")
        self.assertFalse((self.home / "config/.env").exists())

    def test_prerequisite_failures_never_download_or_write_config(self):
        cases = [({**self.checks, "tailscaleReady": False}, "collie", None, "Tailscale"),
                 (self.checks, "/missing/custom", None, "custom"),
                 ({**self.checks, "muxes": []}, "collie", None, "herdr")]
        for checks, requested, binary, error in cases:
            with self.subTest(error=error), patch.object(c, "prerequisites", return_value=checks), patch.object(c, "executable", return_value=binary), patch.object(c, "run") as run, patch.object(c, "seed_config") as seed, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, error):
                    c.deploy(requested, 8787, "herdr")
                run.assert_not_called()
                seed.assert_not_called()

    def test_existing_backend_skips_installer_and_verifies_health(self):
        output = io.StringIO()
        ready = {"healthy": True, "tailnetPublished": True}
        with patch.object(c, "prerequisites", return_value=self.checks), patch.object(c, "executable", return_value="collie"), patch.object(c, "seed_config"), patch.object(c, "run", return_value=result()) as run, patch.object(c, "status", return_value=ready), contextlib.redirect_stdout(output):
            answer = c.deploy("collie", 8787, "herdr")
        self.assertTrue(answer["ok"])
        self.assertEqual(run.call_args.args[0], ["collie", "start", "--plain"])
        self.assertEqual([json.loads(line)["stage"] for line in output.getvalue().splitlines()], [0, 2, 3, 4])

    def test_missing_route_is_reported_as_partial_setup(self):
        with patch.object(c, "prerequisites", return_value=self.checks), patch.object(c, "executable", return_value="collie"), patch.object(c, "seed_config"), patch.object(c, "run", return_value=result()), patch.object(c, "status", return_value={"healthy": True, "tailnetPublished": False}), contextlib.redirect_stdout(io.StringIO()):
            answer = c.deploy("collie", 8787, "herdr")
        self.assertFalse(answer["ok"])
        self.assertIn("Enable HTTPS", answer["message"])

    def test_download_failure_stops_before_configuration_and_start(self):
        with patch.object(c, "prerequisites", return_value=self.checks), patch.object(c, "executable", return_value=None), patch.object(c.shutil, "which", return_value="tool"), patch.object(c, "run", return_value=result(stderr="offline", code=1)) as run, patch.object(c, "seed_config") as seed, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                c.deploy("collie", 8787, "herdr")
        seed.assert_not_called()
        self.assertEqual(run.call_count, 1)
        self.assertTrue(run.call_args.args[0][-1].endswith("/v1.16.2/collie-1.16.2-linux-x64.tar.gz"))

    def test_install_uses_fixed_package_names_and_reports_cancel(self):
        with patch.object(c, "run", return_value=result(stderr="Cancelled", code=126)) as run:
            answer = c.install_requirement("install-qr", "herdr")
        self.assertFalse(answer["ok"])
        self.assertEqual(run.call_args.args[0], ["/usr/bin/pkexec", "/usr/bin/pacman", "-S", "--needed", "--noconfirm", "qrencode"])

    def test_install_deps_requests_every_missing_package_in_one_prompt(self):
        checks = {"tailscaleInstalled": False, "muxes": [], "qrAvailable": False, "missingTools": ["curl"]}
        with patch.object(c, "prerequisites", return_value=checks), patch.object(c, "run", return_value=result()) as run:
            answer = c.install_requirement("install-deps", "tmux", None)
        self.assertTrue(answer["ok"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/pkexec", "/usr/bin/pacman", "-S", "--needed", "--noconfirm",
                                                 "tailscale", "tmux", "qrencode", "curl"])

    def test_install_deps_for_an_installed_backend_skips_setup_only_packages(self):
        checks = {"tailscaleInstalled": True, "muxes": [], "qrAvailable": False, "missingTools": ["curl"]}
        with patch.object(c, "prerequisites", return_value=checks), patch.object(c, "run") as run:
            answer = c.install_requirement("install-deps", "herdr", "/usr/bin/collie")
        self.assertTrue(answer["ok"])
        run.assert_not_called()

    def test_setup_lock_blocks_duplicate_install(self):
        folder = self.home / "runtime"
        folder.mkdir()
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(folder)}), patch.object(c, "deploy", return_value={"ok": True}):
            lock_dir = folder / "collie-lab"
            lock_dir.mkdir()
            (lock_dir / "setup.lock").touch(mode=0o600)
            with open(lock_dir / "setup.lock", "a") as lock:
                c.fcntl.flock(lock, c.fcntl.LOCK_EX | c.fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    c.setup("collie", 8787, "herdr")
            self.assertTrue(c.setup("collie", 8787, "herdr")["ok"])

    def test_clean_install_verifies_release_and_is_safe_to_retry(self):
        import hashlib, io, tarfile
        archive = self.home / "fixture.tar.gz"
        prefix = "collie-1.16.2-linux-x64"
        with tarfile.open(archive, "w:gz") as tar:
            payload = b"#!/bin/sh\nexit 0\n"
            entry = tarfile.TarInfo(prefix + "/bin/collie")
            entry.mode = 0o755; entry.size = len(payload)
            tar.addfile(entry, io.BytesIO(payload))
        metadata = {"version":"1.16.2", "repository":"AltanS/collie",
                    "platforms":{"linux-x64":hashlib.sha256(archive.read_bytes()).hexdigest()}}
        binary = self.home / ".local/share/collie/current/bin/collie"
        folder = self.home / "config"
        real_run = c.run
        downloads = []
        def resolve(name): return str(binary) if binary.exists() else None
        def invoke(argv, **kwargs):
            if argv[0] == "/usr/bin/curl":
                target = Path(argv[argv.index("--output") + 1])
                target.write_bytes(archive.read_bytes()); downloads.append(target)
                return result()
            return real_run(argv, **kwargs)
        with patch.dict(os.environ, {"HOME":str(self.home)}), patch.object(c.platform,"machine",return_value="x86_64"), patch.object(c,"release_metadata",return_value=metadata), patch.object(c,"prerequisites",return_value=self.checks), patch.object(c,"executable",side_effect=resolve), patch.object(c,"config_directory",return_value=folder), patch.object(c,"run",side_effect=invoke), patch.object(c,"status",return_value={"healthy":True,"tailnetPublished":True}), contextlib.redirect_stdout(io.StringIO()):
            first=c.deploy("collie",9000,"herdr")
            before=(folder/".env").read_bytes()
            second=c.deploy("collie",9000,"herdr")
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(len(downloads),1)
        self.assertEqual((folder/".env").read_bytes(),before)
        self.assertFalse(downloads[0].exists())


if __name__ == "__main__":
    unittest.main()
