"""OrderTrack Pro - one command to run everything.

    python run.py            install what is missing, build the UI if needed, start on http://localhost:8000
    python run.py --dev      developer mode: auto-reloading backend + live-reloading UI on http://localhost:5173
    python run.py --test     run the automated test suite
    python run.py --port 9000 --no-browser
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
REQUIRED_MODULES = ["fastapi", "uvicorn", "sqlalchemy", "multipart", "jwt", "bcrypt", "openpyxl", "xlrd",
                    "numpy", "scipy", "sklearn", "joblib", "rapidfuzz", "reportlab"]


def say(msg: str) -> None:
    print(f"\033[96m==>\033[0m {msg}", flush=True)


def ensure_python() -> None:
    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11 or newer is required (found {sys.version.split()[0]}). Install it from https://www.python.org")


def ensure_backend_deps(dev: bool = False) -> None:
    missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    if dev and importlib.util.find_spec("pytest") is None:
        missing.append("pytest")
    if missing:
        say(f"Installing Python packages ({', '.join(missing)} missing) - first run only, takes a few minutes…")
        req = BACKEND / ("requirements-dev.txt" if dev else "requirements.txt")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req)], cwd=BACKEND)


def npm() -> str | None:
    return shutil.which("npm.cmd") or shutil.which("npm")


def newest_mtime(paths) -> float:
    latest = 0.0
    for p in paths:
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    latest = max(latest, f.stat().st_mtime)
        elif p.exists():
            latest = max(latest, p.stat().st_mtime)
    return latest


def ensure_frontend(dev: bool) -> bool:
    """Make sure the UI can be served. Returns False if Node.js is unavailable and no build exists."""
    dist = FRONTEND / "dist" / "index.html"
    npm_cmd = npm()
    if not npm_cmd:
        if dev or not dist.exists():
            print("\n  Node.js is not installed, so the user interface cannot be built.\n"
                  "  Install the LTS version from https://nodejs.org and run this command again.\n")
            return dist.exists() and not dev
        return True
    if not (FRONTEND / "node_modules").exists():
        say("Installing UI packages - first run only…")
        subprocess.check_call([npm_cmd, "install", "--no-audit", "--no-fund"], cwd=FRONTEND)
    if dev:
        return True
    sources = [FRONTEND / "src", FRONTEND / "index.html", FRONTEND / "package.json", FRONTEND / "public",
               FRONTEND / "vite.config.ts"]
    if not dist.exists() or newest_mtime(sources) > dist.stat().st_mtime:
        say("Building the user interface…")
        env = {**os.environ, "VITE_API_URL": ""}          # served by this same server
        subprocess.check_call([npm_cmd, "run", "build"], cwd=FRONTEND, env=env)
    return True


def open_when_ready(url: str, health: str) -> None:
    def wait():
        for _ in range(240):
            try:
                with urllib.request.urlopen(health, timeout=2):
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        print(f"\n  \033[92mOrderTrack Pro is running:\033[0m {url}\n  Press Ctrl+C in this window to stop.\n", flush=True)
        webbrowser.open(url)
    threading.Thread(target=wait, daemon=True).start()


def run_server(port: int, reload: bool) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port)]
    if reload:
        cmd += ["--reload", "--reload-dir", "app"]
    return subprocess.Popen(cmd, cwd=BACKEND)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run OrderTrack Pro")
    ap.add_argument("--dev", action="store_true", help="developer mode with auto-reload (UI on port 5173)")
    ap.add_argument("--test", action="store_true", help="run the automated tests and exit")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    ensure_python()
    os.chdir(ROOT)
    ensure_backend_deps(dev=args.test)
    if args.test:
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "tests"], cwd=BACKEND))

    if not ensure_frontend(args.dev):
        say("Starting the API only (no user interface).")
    procs: list[subprocess.Popen] = [run_server(args.port, reload=args.dev)]
    if args.dev:
        say("Starting the UI dev server on http://localhost:5173 …")
        procs.append(subprocess.Popen([npm(), "run", "dev"], cwd=FRONTEND))
        url = "http://localhost:5173"
    else:
        url = f"http://localhost:{args.port}"
    if not args.no_browser:
        open_when_ready(url, f"http://127.0.0.1:{args.port}/api/health")
    else:
        print(f"\n  OrderTrack Pro: {url}  (Ctrl+C to stop)\n", flush=True)

    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        say("Stopping…")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
