#!/usr/bin/env python3
"""Native UI scenario checks. Requires Omarchy, Quickshell, qrencode and zbarimg.

All install/service actions are simulated; runs a fictional preview inside an omabox desktop.
"""
import json, os, subprocess, tempfile, time
from pathlib import Path
workspace=Path(__file__).resolve().parents[1]
out=Path(os.environ.get('COLLIE_LAB_ARTIFACTS') or tempfile.mkdtemp(prefix='collie-lab-verification-'))
out.mkdir(exist_ok=True)
for scenario in ('missing','no-qr','offline','error','ready'):
    with tempfile.TemporaryFile(mode='w+') as logs:
        proc=subprocess.Popen(['bash','tests/preview.sh',scenario],cwd=workspace,stdout=logs,stderr=logs)
        config=None
        try:
            for _ in range(50):
                logs.seek(0); data=logs.read()
                if 'Preview: ' in data:
                    config=data.split('Preview: ',1)[1].splitlines()[0]+'/shell.qml'
                if 'Configuration Loaded' in data: break
                if proc.poll() is not None: raise RuntimeError(data)
                time.sleep(.1)
            time.sleep(1.1)
            def call(target,method,*args):
                return subprocess.check_output(['qs','-p',config,'ipc','call',target,method,*args],text=True).strip()
            def inspect(): return json.loads(call('labtest','inspect'))
            def act(action):
                call('labtest','act',action)
                for _ in range(50):
                    time.sleep(.1)
                    if not inspect()['busy']: break
                call('overp0werj0int.collie','refresh')
                time.sleep(.2)
            call('labtest','capture',str(out/(scenario+'.png')))
            focus=json.loads(call('labtest','focusWalk'))
            def until(predicate, seconds=20):
                for _ in range(int(seconds*10)):
                    state=inspect()
                    if predicate(state): return state
                    time.sleep(.1)
                raise AssertionError(inspect())
            def decode(name):
                call('labtest','capture',str(out/name)); time.sleep(.3)
                return subprocess.check_output(['zbarimg','--quiet',str(out/name)],text=True,stderr=subprocess.DEVNULL)
            if scenario=='missing':
                assert focus==['Set up Collie'], focus # one obvious next action, focused on open
                call('labtest','setup')
                # Requirements, Tailscale sign-in, install, start, publish and verify: one request.
                state=until(lambda s: s['ready'] and not s['busy'] and not s['setupRunning'])
                assert state['nextStep']=='' and not state['error']
                # Ready shows the choices; nothing is minted until one is made.
                time.sleep(.6); state=inspect()
                assert state['mode']=='' and state['codeCleared'] and not state['makingCode'], state
                walk=json.loads(call('labtest','focusWalk'))
                assert walk[:1]==['Choose how to connect'] and 'Open on this computer' in walk, walk
                call('labtest','mode','control')
                until(lambda s: s['pairingQr'])
                decoded=decode('pair-demo-final.png')
                assert '/settings?pair=DEMO-ONLY' in decoded and 'name=' not in decoded, decoded
                # A device name rides in the same link; the code and its countdown stay.
                call('labtest','deviceName','iPad mini')
                until(lambda s: s['qrName']=='iPad mini')
                decoded=decode('pair-named-demo.png')
                assert 'pair=DEMO-ONLY&name=iPad%20mini' in decoded, decoded
                call('labtest','expirePair')
                # An expired code says so and waits for a new one; no silent renewal, no error.
                state=until(lambda s: s['pairExpired'])
                time.sleep(1.5); state=inspect()
                assert not state['pairing'] and not state['makingCode'] and not state['error'], state
                call('labtest','capture',str(out/'expired-demo.png'))
                call('labtest','key','n')
                state=until(lambda s: s['pairingQr'])
                assert not state['pairExpired']
            elif scenario=='ready':
                assert inspect()['opened']
                assert call('labtest','ownershipProbe')=='true'
                call('overp0werj0int.collie','open'); call('overp0werj0int.collie','open')
                assert inspect()['opened']
                time.sleep(.6); state=inspect()
                assert state['mode']=='' and state['codeCleared'] and not state['makingCode'], state
                call('labtest','capture',str(out/'ready-demo.png'))
                call('labtest','mode','control')
                until(lambda s: s['pairingQr'])
                call('labtest','capture',str(out/'control-demo.png'))
                call('overp0werj0int.collie','close')
                state=inspect(); assert state['codeCleared'] and state['qrCleared'] and state['mode']==''
                call('overp0werj0int.collie','open')
                time.sleep(.6); assert inspect()['codeCleared'] # reopening starts at the choice
                call('labtest','mode','control')
                until(lambda s: s['pairingQr'])
                call('labtest','settingsPort','9000')
                assert inspect()['codeCleared'] # a settings change drops the old code
                until(lambda s: s['pairingQr']) # and Full control makes a fresh one
                status=json.loads(call('overp0werj0int.collie','status'))
                assert 'DEMO-ONLY' not in json.dumps(status) and status['mode']=='control' # IPC never exposes the code
                call('labtest','goBack'); assert inspect()['mode']=='' and inspect()['opened']
                call('labtest','mode','watch'); time.sleep(.6)
                decoded=decode('watch-demo.png')
                assert 'collie-demo.example.ts.net' in decoded and 'pair=' not in decoded, decoded
                call('labtest','orientation','left'); time.sleep(.2)
                call('labtest','capture',str(out/'vertical-demo.png'))
                call('labtest','orientation','top'); time.sleep(.3)
                call('labtest','key','o') # this computer: its own window, and the panel gets out of the way
                until(lambda s: not s['opened'] and not s['busy'])
            elif scenario=='no-qr':
                call('labtest','mode','watch'); time.sleep(.3)
                assert 'Install QR tool' in json.loads(call('labtest','focusWalk'))
                act('install-qr'); time.sleep(.4)
                assert 'Install QR tool' not in json.loads(call('labtest','focusWalk'))
            elif scenario=='offline':
                assert 'Start bridge' in focus
                assert inspect()['nextStep']=='bridge'
                call('labtest','setup') # starts the bridge, then publishes the route
                state=until(lambda s: s['ready'] and not s['busy'] and not s['setupRunning'])
                assert not state['error']
            elif scenario=='error':
                act('setup'); state=inspect(); assert state['error'] and state['stage']==1
                assert 'Try setup again' in json.loads(call('labtest','focusWalk'))
                call('labtest','capture',str(out/'install-error.png'))
            print(json.dumps({'scenario':scenario,'result':'passed','focusControls':len(focus)}),flush=True)
            logs.seek(0); data=logs.read()
            scene=[line for line in data.splitlines() if 'WARN scene:' in line or 'ERROR' in line]
            assert not scene, scene
        finally:
            if config: subprocess.run(['qs','-p',config,'kill'],capture_output=True)
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired: proc.terminate(); proc.wait(timeout=5)

print("Verification artifacts:", out)
