# Wrapper that imports root server.py so Docker build context stays local to addon folder
from pathlib import Path
import runpy, sys

root_server = Path(__file__).resolve().parent.parent / 'server.py'
if not root_server.exists():
    print('ERROR: Root server.py not found at', root_server)
    sys.exit(1)
runpy.run_path(str(root_server))
