"""Start both development services. Stop both with Ctrl+C."""
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[1]
children=[]
try:
    children.append(subprocess.Popen([sys.executable,'-m','uvicorn','server.app:app','--host','127.0.0.1','--port','8000'],cwd=root))
    children.append(subprocess.Popen(['npm','run','dev'],cwd=root/'web'))
    print('Danish Dynaword explorer: http://localhost:5173',flush=True)
    while all(child.poll() is None for child in children):time.sleep(.5)
finally:
    for child in children:
        if child.poll() is None:child.terminate()
    for child in children:
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill()
