"""Own and terminate the entire local worker process tree."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class ProcessTree:
    def __init__(self, process, deadline, environment):
        self.process, self.job = process, None
        self.watchdog, self.watchdog_writer = None, None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            # The research supervisor needs kill-on-close ownership, not a memory cap.
            class Basic(ctypes.Structure):
                _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                            ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                            ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                            ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
            class IoCounters(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
            class Extended(ctypes.Structure):
                _fields_ = [("basic", Basic), ("io", IoCounters),
                            ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                            ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel = kernel
            self.job = kernel.CreateJobObjectW(None, None)
            limits = Extended()
            limits.basic.flags = 0x2000
            if not self.job or not kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                self.close()
                raise OSError("Cannot configure process-tree supervision")
            handle = kernel.OpenProcess(0x0101, False, process.pid)
            try:
                if not handle or not kernel.AssignProcessToJobObject(self.job, handle):
                    self.close()
                    raise OSError("Cannot supervise worker process tree")
            finally:
                if handle:
                    kernel.CloseHandle(handle)
        else:
            import select
            read_fd, write_fd = os.pipe()
            self.watchdog_writer = write_fd
            try:
                self.watchdog = subprocess.Popen(
                    [sys.executable, "-I", str(Path(__file__).with_name("session_watchdog.py")), str(process.pid), str(read_fd)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    pass_fds=(read_fd,), start_new_session=True, env=environment,
                )
                readable, _, _ = select.select([self.watchdog.stdout], [], [], max(0, deadline - time.monotonic()))
                if not readable:
                    raise subprocess.TimeoutExpired(process.args, max(0, deadline - time.monotonic()))
                if os.read(self.watchdog.stdout.fileno(), 6) != b"READY\n":
                    raise OSError("Lifetime watchdog did not become ready")
            except BaseException:
                self.close()
                raise
            finally:
                os.close(read_fd)

    def close(self):
        if self.job is not None:
            self.kernel.CloseHandle(self.job)
            self.job = None
        elif os.name != "nt":
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if self.watchdog_writer is not None:
                os.close(self.watchdog_writer)
                self.watchdog_writer = None
            if self.watchdog is not None:
                try:
                    self.watchdog.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.watchdog.kill()
                    self.watchdog.wait()


def supervised_json_process(script: Path, payload: dict, timeout: float) -> dict:
    if os.name != "nt" and sys.platform != "linux":
        raise OSError("Managed process ownership currently supports Windows and Linux only")
    deadline = time.monotonic() + timeout
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "COMSPEC", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"}
                   or key.startswith("COVERAGE_")}
    environment.update(PYTHONIOENCODING="utf-8", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    process = subprocess.Popen([sys.executable, "-I", str(script), str(os.getpid())], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                               env=environment, cwd=script.parents[2],
                               start_new_session=os.name != "nt", creationflags=0x08000000 if os.name == "nt" else 0)
    tree = None
    try:
        tree = ProcessTree(process, deadline, environment)
        stdout, stderr = process.communicate(json.dumps(payload), timeout=max(0.001, deadline - time.monotonic()))
        if process.returncode:
            raise RuntimeError(f"Workflow worker exited with code {process.returncode}")
        return json.loads(stdout)
    finally:
        if tree is not None:
            tree.close()
        if process.poll() is None:
            process.kill()
        process.communicate()
