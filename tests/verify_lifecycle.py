#!/usr/bin/env python3
"""Writable Git lifecycle fixture. Run only inside an omabox desktop."""
import json, os, shutil, subprocess, tempfile, time
from pathlib import Path

if Path.home() != Path('/home/sbx'):
    raise SystemExit('Run this fixture inside omabox; it changes only the private desktop.')
root=Path(__file__).resolve().parents[1]
fixture_id='overp0werj0int.collie.review-fixture'
installed=Path.home()/'.config/omarchy/plugins'/fixture_id
if installed.exists(): raise SystemExit('A previous lifecycle fixture exists; inspect it before retrying.')

def run(*argv):
    return subprocess.run(argv,check=True,capture_output=True,text=True).stdout.strip()
def commit(repo,message):
    run('git','-C',str(repo),'add','.')
    run('git','-C',str(repo),'-c','user.name=Collie fixture','-c','user.email=fixture@example.invalid','commit','-qm',message)

with tempfile.TemporaryDirectory(prefix='collie-lifecycle-') as folder:
    source=Path(folder)/'source';source.mkdir()
    for name in ('ColliePanel.qml','IpcOwner.js','manifest.json','LICENSE','README.md','scripts'):
        path=root/name
        if path.is_dir():shutil.copytree(path,source/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:shutil.copy2(path,source/name)
    manifest=json.loads((source/'manifest.json').read_text());manifest['id']=fixture_id
    (source/'manifest.json').write_text(json.dumps(manifest))
    panel=source/'ColliePanel.qml';panel.write_text(panel.read_text().replace('overp0werj0int.collie',fixture_id))
    run('git','init','-q',str(source));commit(source,'Reviewed fixture')
    run('git','clone','--quiet',str(source),str(installed))
    marker=Path.home()/'collie-backend-retained.fixture';marker.write_text('backend data stays')
    try:
        run('omarchy','plugin','validate',str(installed))
        run('omarchy-shell','shell','rescanPlugins')
        deadline=time.monotonic()+5
        while True:
            result=subprocess.run(['omarchy','plugin','enable',fixture_id],capture_output=True,text=True)
            if result.returncode==0:break
            if time.monotonic()>deadline:raise RuntimeError(result.stderr+result.stdout)
            time.sleep(.1)
        run('omarchy','plugin','disable',fixture_id)
        run('omarchy','plugin','enable',fixture_id)
        (source/'fixture-update.txt').write_text('fast-forward update')
        commit(source,'Fixture update')
        run('omarchy','plugin','update',fixture_id,'--yes')
        assert (installed/'fixture-update.txt').read_text()=='fast-forward update'
        run('omarchy','plugin','remove',fixture_id,'--yes')
        assert not installed.exists()
        assert marker.read_text()=='backend data stays'
        print(json.dumps({'writableGitClone':True,'disableEnable':'passed','fastForwardUpdate':'passed','removal':'passed','retainedMarker':'passed'}))
    finally:
        if installed.exists():
            subprocess.run(['omarchy','plugin','remove',fixture_id,'--yes'],capture_output=True)
        marker.unlink(missing_ok=True)
