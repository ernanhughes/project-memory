"""Bounded subprocesses; timeouts must not leave model workers running."""
from __future__ import annotations

import os
import signal
import subprocess


def run_bounded(command: list[str], *, cwd: str, timeout: float):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", **options)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        if os.name == "nt":
            # Process termination only: no shell or filesystem operations.
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
