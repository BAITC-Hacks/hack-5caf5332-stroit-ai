"""Copy only deliverables, bootstrap from zero, run API + test suite; retain logs."""
from pathlib import Path
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request,urlopen

root=Path(__file__).resolve().parent.parent
work=Path(tempfile.mkdtemp(prefix='orgstructure-clean-'))
for folder in ('app','static','data','test','docs'):
    shutil.copytree(root/folder,work/folder,ignore=shutil.ignore_patterns('__pycache__'))
for name in ('requirements.txt','README.md'):
    shutil.copy2(root/name,work/name)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env={k:v for k,v in os.environ.items() if k not in ('OPENAI_API_KEY','ENABLE_LLM','PYTHONPATH','VIRTUAL_ENV')}
env.update(PORT=str(port),HOST='127.0.0.1')
log=open(work/'startup.log','w')
server=subprocess.Popen([sys.executable,'-m','app'],cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT)
base=f'http://127.0.0.1:{port}'
try:
    ready=False
    for _ in range(240):
        if server.poll() is not None:raise RuntimeError('Server exited: '+(work/'startup.log').read_text())
        try:
            with urlopen(base+'/api/health',timeout=1) as r:ready=json.load(r)['status']=='ok'
            if ready:break
        except OSError:time.sleep(.25)
    if not ready:raise RuntimeError('Bootstrap timed out; see '+str(work/'startup.log'))
    with urlopen(Request(base+'/api/demo',data=b''),timeout=20) as r:report=json.load(r)
    assert report['mode']=='deterministic'
    for fmt in ('html','json'):
        with urlopen(base+'/api/export/'+report['run_id']+'?format='+fmt) as r:assert len(r.read())>1000
    python=work/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(python),'-m','unittest','discover','-s','test','-v'],cwd=work,env=env,check=True)
    print('CLEAN START: PASS; no API keys; health, demo, exports, all tests passed.')
    print('Retained clean directory and startup log:',work)
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
    log.close()
