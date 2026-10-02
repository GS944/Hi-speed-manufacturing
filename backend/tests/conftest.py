import os
import sys
import tempfile
from pathlib import Path

# isolated data directory for the whole test session (must be set before `app` is imported)
_tmp = tempfile.mkdtemp(prefix="ordertrack-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "Test@12345"
os.environ.setdefault("STATIC_DIR", str(Path(_tmp) / "no-static"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
