"""One-command bootstrap. No keys and no frontend build required."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
venv = root / '.venv'
python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
if Path(sys.prefix).resolve() != venv.resolve():
    if not python.exists():
        subprocess.check_call([sys.executable, '-m', 'venv', str(venv)])
    stamp = venv / '.requirements'
    requirements = (root / 'requirements.txt').read_text()
    if not stamp.exists() or stamp.read_text() != requirements:
        subprocess.check_call([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements.txt')])
        stamp.write_text(requirements)
    os.execv(str(python), [str(python), '-m', 'app', *sys.argv[1:]])
from .server import serve
serve()
