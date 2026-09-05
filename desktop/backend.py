"""Hidden desktop entry point; keep logs/temp on the project drive.

The local service can be shared with the browser. Closing a desktop window does
not kill jobs or a service another editor is using. A later launch reuses it.
"""
import os
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent.parent
logs = root / "data" / "logs"
temp = root / "data" / "temp"
logs.mkdir(parents=True, exist_ok=True)
temp.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = str(temp)
os.environ["PYTHONUTF8"] = "1"
sys.stdout = (logs / "server-output.log").open("a", encoding="utf-8", buffering=1)
sys.stderr = (logs / "server-error.log").open("a", encoding="utf-8", buffering=1)
sys.path.insert(0, str(root))
os.chdir(root)
sys.argv = [str(root / "app.py")]
try:
    runpy.run_path(str(root / "app.py"), run_name="__main__")
except BaseException:
    import traceback
    traceback.print_exc()
    raise
