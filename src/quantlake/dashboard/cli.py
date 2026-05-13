"""Launcher for the dashboard: builds the React app if needed, starts uvicorn."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_ROOT / "dashboard"
FRONTEND_DIST = FRONTEND_DIR / "dist"


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"  $ {' '.join(cmd)}  (cwd={cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def _ensure_frontend_build(force: bool = False) -> None:
    if not FRONTEND_DIR.exists():
        print(f"[dashboard] No frontend directory at {FRONTEND_DIR} — skipping build.")
        return
    if FRONTEND_DIST.exists() and not force:
        print("[dashboard] Frontend build found, skipping (use --rebuild to force).")
        return
    npm = shutil.which("npm")
    if npm is None:
        print("[dashboard] npm not found in PATH — cannot build the frontend.")
        sys.exit(1)
    if not (FRONTEND_DIR / "node_modules").exists():
        _run([npm, "install"], cwd=FRONTEND_DIR)
    _run([npm, "run", "build"], cwd=FRONTEND_DIR)


def _open_browser(url: str, delay: float = 1.5) -> None:
    def _later():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_later, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantLake dashboard launcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of the frontend")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    parser.add_argument("--reload", action="store_true", help="Enable FastAPI reload (dev)")
    args = parser.parse_args()

    _ensure_frontend_build(force=args.rebuild)

    url = f"http://{args.host}:{args.port}"
    print(f"[dashboard] Starting on {url}")
    if not args.no_browser:
        _open_browser(url)

    uvicorn.run(
        "quantlake.dashboard.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
