"""Adversarial probes of production process, URL and file boundaries."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from test_control import c, result


class SecurityTests(unittest.TestCase):
    def test_real_pipe_overflow_is_bounded_before_parse(self):
        for pipe in ('stdout', 'stderr'):
            with self.subTest(pipe=pipe):
                with self.assertRaisesRegex(RuntimeError, 'safety limit'):
                    c.run([sys.executable, '-c', f'import sys; sys.{pipe}.write("x" * 100000)'], output_limit=4096)

    def test_unterminated_drip_output_has_total_deadline(self):
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            c.run([sys.executable, '-c', 'import os,time\nwhile True: os.write(1,b"x"); time.sleep(.02)'], timeout=.2)
        self.assertLess(time.monotonic() - started, 2)

    def test_timeout_does_not_echo_partial_secrets(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out') as error:
            c.run([sys.executable, '-c', 'import os,time; os.write(1,b"SECRET-PAIR-CODE"); time.sleep(10)'], timeout=.2)
        self.assertNotIn('SECRET', str(error.exception))

    def test_descendant_cannot_keep_pipes_alive_after_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'survived'
            script = 'import subprocess,time,sys; subprocess.Popen([sys.executable,"-c", "import time,pathlib; time.sleep(.5); pathlib.Path("+repr(sys.argv[1])+").touch()"]); time.sleep(5)'
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                c.run([sys.executable, '-c', script, str(marker)], timeout=.15)
            time.sleep(.55)
            self.assertFalse(marker.exists())

    def test_cancelled_helper_reaps_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'survived'
            script = '''import importlib.util,signal,sys
spec=importlib.util.spec_from_file_location("c",sys.argv[1]); c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
signal.signal(signal.SIGTERM,c.interrupted)
c.run([sys.executable,"-c","import pathlib,time; pathlib.Path("+repr(sys.argv[2])+"+'.ready').touch(); time.sleep(.6); pathlib.Path("+repr(sys.argv[2])+").touch()"],timeout=5)
'''
            proc = subprocess.Popen([sys.executable, '-c', script, c.__file__, str(marker)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 3
                while not Path(str(marker)+'.ready').exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(Path(str(marker)+'.ready').exists())
                proc.terminate(); proc.communicate(timeout=2)
                time.sleep(.65)
                self.assertFalse(marker.exists())
            finally:
                if proc.poll() is None: proc.kill(); proc.communicate()

    def test_binary_and_stdin_are_preserved(self):
        answer = c.run([sys.executable, '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'], input_text=b'hello\x00', binary=True)
        self.assertEqual(answer.stdout, b'hello\x00')
        self.assertEqual(answer.returncode, 0)

    def test_nested_tailscale_payloads_fail_safely(self):
        for payload in ({'Self':None,'User':[]}, {'Self':[],'User':None}, {'Self':{'UserID':1},'User':{'1':[]}}):
            with patch.object(c.shutil,'which',return_value='tool'), patch.object(c,'executable',return_value='tool'), patch.object(c,'run',return_value=result(json.dumps(payload))):
                self.assertEqual(c.prerequisites()['trustedUser'], '')

    def test_ambiguous_url_is_rejected(self):
        for url in ('https://host.ts.net/?token=secret','https://host.ts.net/#pair','https://host.ts.net:invalid','https://host.ts.net:70000'):
            with patch.object(c,'run',return_value=result(url)):
                with self.assertRaises(RuntimeError): c.app_url('collie')

    def test_failed_pairing_does_not_expose_code(self):
        with patch.object(c,'run',return_value=result('SECRET-PAIR-CODE',code=1)):
            with self.assertRaises(RuntimeError) as failure: c.action('collie','pair')
        self.assertNotIn('SECRET',str(failure.exception))

    def test_redrawn_pairing_code_never_travels_on_argv(self):
        with patch.dict(os.environ,{'COLLIE_LAB_PAIR_CODE':'ABCD2345'}), patch.object(c,'app_url',return_value='https://host.ts.net'), patch.object(c,'qr_image',return_value='image') as qr, patch.object(c,'run') as run:
            self.assertEqual(c.action('collie','pair-qr','iPad')['qr'],'image')
        self.assertIn('pair=ABCD2345',qr.call_args.args[0]); run.assert_not_called()
        for code in ('','a b','../x','A'*200):
            with self.subTest(code=code), patch.dict(os.environ,{'COLLIE_LAB_PAIR_CODE':code}):
                with self.assertRaises(RuntimeError): c.action('collie','pair-qr')

    def test_readable_lock_from_an_older_version_is_tightened_not_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'collie-lab').mkdir(mode=0o700)
            lock=Path(folder)/'collie-lab/setup.lock'; lock.touch(); lock.chmod(0o644)
            with patch.dict(os.environ,{'XDG_RUNTIME_DIR':folder}):
                self.assertEqual(c.locked_operation(lambda:'ran'),'ran')
            self.assertEqual(lock.stat().st_mode & 0o777, 0o600)

    def test_symlink_directory_and_lock_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'actual').mkdir(); (root/'link').symlink_to(root/'actual')
            with self.assertRaises(OSError): c.private_directory(root/'link'/'config')
            runtime=root/'runtime'; (runtime/'collie-lab').mkdir(parents=True)
            victim=root/'victim'; victim.write_text('untouched')
            (runtime/'collie-lab/setup.lock').symlink_to(victim)
            with patch.dict(os.environ,{'XDG_RUNTIME_DIR':str(runtime)}):
                with self.assertRaises(OSError): c.locked_operation(lambda:None)
            self.assertEqual(victim.read_text(),'untouched')

    def test_timeout_json_never_contains_captured_output(self):
        with patch.object(c.sys,'argv',['control.py','restart']), patch.object(c,'executable',return_value='collie'), patch.object(c,'locked_operation',side_effect=subprocess.TimeoutExpired('collie',60,output='SECRET')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(c.main(),1)
        self.assertNotIn('SECRET',output.getvalue())

    def test_all_loopback_variants_are_not_phone_urls(self):
        for url in ('http://127.0.0.2','http://0.0.0.0','http://[::]','http://[::ffff:127.0.0.1]','http://localhost.','http://a.localhost'):
            self.assertFalse(c.phone_url(url),url)

    def test_unsafe_release_entries_are_rejected(self):
        import tarfile
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'payload.tar.gz'
            for kind in ('escape','absolute','symlink','hardlink','oversize','duplicate'):
                with self.subTest(kind=kind):
                    with tarfile.open(archive,'w:gz') as tar:
                        name={'escape':'collie/../escape','absolute':'/tmp/escape'}.get(kind,'collie/data')
                        entry=tarfile.TarInfo(name)
                        if kind in ('symlink','hardlink'):
                            entry.type=tarfile.SYMTYPE if kind=='symlink' else tarfile.LNKTYPE
                            entry.linkname='/tmp/escape'
                        elif kind=='oversize': entry.size=0
                        tar.addfile(entry)
                        if kind=='duplicate': tar.addfile(entry)
                    if kind=='oversize':
                        import gzip
                        entry.size=600*1024*1024
                        with gzip.open(archive,'wb') as raw: raw.write(entry.tobuf()+b'\0'*1024)
                    with self.assertRaises(RuntimeError): c.extract_release(archive,folder,'collie')

    def test_checksum_mismatch_never_installs_or_executes(self):
        with tempfile.TemporaryDirectory() as folder:
            metadata={'version':'1.16.2','repository':'AltanS/collie','platforms':{'linux-x64':'0'*64}}
            def download(argv,**kwargs):
                Path(argv[argv.index('--output')+1]).write_bytes(b'not a release')
                return result()
            with patch.object(c.Path,'home',return_value=Path(folder)), patch.object(c.platform,'machine',return_value='x86_64'), patch.object(c,'release_metadata',return_value=metadata), patch.object(c,'run',side_effect=download) as run:
                with self.assertRaisesRegex(RuntimeError,'checksum mismatch'): c.install_release()
            self.assertEqual(run.call_count,1)
            self.assertFalse((Path(folder)/'.local/share/collie').exists())

    def test_unrelated_install_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            existing=Path(folder)/'.local/share/collie';existing.mkdir(parents=True)
            marker=existing/'mine';marker.write_text('keep')
            with patch.object(c.Path,'home',return_value=Path(folder)), patch.object(c.platform,'machine',return_value='x86_64'),patch.object(c,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'already exists'): c.install_release()
            run.assert_not_called();self.assertEqual(marker.read_text(),'keep')

    def test_health_redirects_are_not_followed(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import threading
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(302);self.send_header('Location','/must-not-follow');self.end_headers()
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        real_run=c.run
        def invoke(argv,**kwargs):
            if argv[0]=='/usr/bin/curl':return real_run(argv,**kwargs)
            return result(code=1)
        try:
            with patch.object(c,'prerequisites',return_value={}), patch.object(c,'app_url',return_value='https://host.ts.net'),patch.object(c,'run',side_effect=invoke):
                self.assertFalse(c.status('collie',server.server_port)['healthy'])
            self.assertEqual(requests,['/api/health'])
        finally: server.shutdown();server.server_close();thread.join()


if __name__ == '__main__': unittest.main()
