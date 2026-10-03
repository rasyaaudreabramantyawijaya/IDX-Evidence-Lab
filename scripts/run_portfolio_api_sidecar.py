"""Run the local IDX Evidence Lab API for a Live Server UI on port 5500."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 5501
HEALTH_URL = f"http://{HOST}:{PORT}/api/health"
STARTUP_TIMEOUT_SECONDS = 45


def api_is_healthy() -> bool:
    try:
        with urlopen(HEALTH_URL, timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and payload.get("ok") is True
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
        return False


def port_is_free(host: str, port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _terminate_owned_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main() -> int:
    if api_is_healthy():
        print(f"READY: IDX Evidence Lab API at http://{HOST}:{PORT} (already healthy; no duplicate started)", flush=True)
        return 0

    if not port_is_free(HOST, PORT):
        print(
            f"ERROR: port {PORT} is occupied but is not a healthy IDX Evidence Lab API; "
            "no process was stopped. Close the owning app or choose another approved port.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    python = os.environ.get("IDXEL_PYTHON") or sys.executable
    env = os.environ.copy()
    source_path = str(ROOT / "src")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (source_path, env.get("PYTHONPATH", ""))))
    env["IDXEL_PORT"] = str(PORT)
    command = [python, "-m", "idx_evidence_lab.web_app"]

    print(f"STARTING: IDX Evidence Lab API on http://{HOST}:{PORT}", flush=True)
    try:
        process = subprocess.Popen(command, cwd=ROOT, env=env)
    except OSError as exc:
        print(f"ERROR: could not start local API with {python}: {exc}", file=sys.stderr, flush=True)
        return 1

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                print(
                    f"ERROR: local API failed before readiness (exit {exit_code}); "
                    "check the selected Python interpreter and project dependencies.",
                    file=sys.stderr,
                    flush=True,
                )
                return 1
            if api_is_healthy():
                print(f"READY: IDX Evidence Lab API at http://{HOST}:{PORT}", flush=True)
                process.wait()
                return 0
            time.sleep(0.25)

        print(
            f"ERROR: local API did not become healthy within {STARTUP_TIMEOUT_SECONDS}s; "
            "check Python dependencies and the task terminal.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        # This is the child created above, never an arbitrary port owner.
        _terminate_owned_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
