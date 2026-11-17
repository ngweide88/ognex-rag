#!/usr/bin/env python3
"""One-command local development launcher.

    python dev.py

Creates the backend virtual environment on first run, installs Python and Node
dependencies, then starts:

    backend  -> http://127.0.0.1:5000
    frontend -> http://localhost:5731

Works on Windows, macOS and Linux. Requires Python 3.11-3.13 and Node 20+.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
IS_WINDOWS = os.name == "nt"
FRONTEND_PORT = 5731
BACKEND_PORT = 5000


def info(message: str) -> None:
    print(f"[ognex] {message}", flush=True)


def fail(message: str) -> None:
    print(f"[ognex] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def pick_python() -> str:
    """Return an interpreter suitable for the dependency set (3.11-3.13)."""
    if (3, 11) <= sys.version_info[:2] <= (3, 13):
        return sys.executable

    candidates: list[list[str]] = []
    if IS_WINDOWS:
        candidates = [["py", f"-{v}"] for v in ("3.13", "3.12", "3.11")]
    else:
        candidates = [[exe] for exe in ("python3.13", "python3.12", "python3.11")]

    for command in candidates:
        try:
            output = subprocess.check_output(
                command + ["-c", "import sys;print(sys.executable)"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if output:
                return output
        except (OSError, subprocess.CalledProcessError):
            continue

    if sys.version_info >= (3, 11):
        info(f"Python {sys.version_info.major}.{sys.version_info.minor} detected; "
             "3.12 or 3.13 is recommended if installation fails.")
        return sys.executable

    fail("Python 3.11+ is required (3.12 or 3.13 recommended).")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def ensure_venv() -> Path:
    python = venv_python()
    if python.exists():
        return python

    base = pick_python()
    info(f"Creating virtual environment in {VENV} ...")
    subprocess.check_call([base, "-m", "venv", str(VENV)])
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip", "-q"])
    return python


def ensure_python_dependencies(python: Path) -> None:
    requirements = BACKEND / "requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = VENV / "requirements.sha256"
    if marker.exists() and marker.read_text().strip() == digest:
        return

    info("Installing Python dependencies (first run can take a few minutes) ...")
    subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(requirements)])
    marker.write_text(digest)


def ensure_env_file() -> None:
    env_file = BACKEND / ".env"
    if env_file.exists():
        return
    shutil.copyfile(BACKEND / ".env.example", env_file)
    info("Created backend/.env from .env.example (mock model; edit it for a real endpoint).")


def npm_command() -> str:
    npm = shutil.which("npm")
    if not npm:
        fail("Node.js/npm was not found. Install Node 20+ from https://nodejs.org")
    return npm


def ensure_node_modules() -> None:
    if (FRONTEND / "node_modules").exists():
        return
    info("Installing frontend dependencies ...")
    subprocess.check_call([npm_command(), "install"], cwd=FRONTEND)


def lan_address() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        sock.close()
        return address
    except OSError:
        return None


def main() -> None:
    python = ensure_venv()
    ensure_python_dependencies(python)
    ensure_env_file()
    ensure_node_modules()

    info(f"Starting backend on http://127.0.0.1:{BACKEND_PORT}")
    backend_env = os.environ.copy()
    # Disable Flask's reloader: it forks a child that survives a simple
    # terminate() when this launcher is stopped.
    backend_env["APP_DEBUG"] = "false"
    backend = subprocess.Popen([str(python), "run.py"], cwd=BACKEND, env=backend_env)

    time.sleep(1.5)
    address = lan_address()
    info(f"Starting frontend on http://localhost:{FRONTEND_PORT}")
    if address:
        info(f"Phone on the same Wi-Fi: http://{address}:{FRONTEND_PORT}")

    try:
        subprocess.call([npm_command(), "run", "dev"], cwd=FRONTEND)
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
        info("Stopped.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        info("Interrupted.")