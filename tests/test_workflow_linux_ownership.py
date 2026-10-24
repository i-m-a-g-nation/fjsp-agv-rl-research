"""Exercise real process ownership on the current Windows or Linux host."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="Managed runtime supports Windows and Linux")
def test_supervisor_death_terminates_worker_and_descendant(tmp_path):
    root = Path(__file__).resolve().parents[1]
    worker = tmp_path / "worker.py"
    worker.write_text("import sys,json,subprocess,os,time\np=json.loads(sys.stdin.read())\nchild=subprocess.Popen([sys.executable,'-c','import time; time.sleep(999)'])\nwith open(p['pid_file']+'.tmp','w') as f: json.dump([os.getpid(),child.pid],f)\nos.replace(p['pid_file']+'.tmp',p['pid_file'])\ntime.sleep(999)\n", encoding="utf-8")
    owner = tmp_path / "owner.py"
    pid_file = tmp_path / "pids.json"
    owner.write_text(f"import sys\nsys.path.insert(0,{str(root)!r})\nfrom pathlib import Path\nfrom src.ai_workflow.process_supervisor import supervised_json_process\nsupervised_json_process(Path({str(worker)!r}),{{'pid_file':{str(pid_file)!r}}},60)\n", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(owner)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    identifiers = []
    def alive(identifier):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, identifier)
            if not handle:
                return False
            try:
                code = wintypes.DWORD()
                return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
            finally:
                kernel.CloseHandle(handle)
        stat = Path(f"/proc/{identifier}/stat")
        return stat.exists() and stat.read_text().split()[2] != "Z"
    try:
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pid_file.exists(), "Worker never started under its lifetime monitor"
        identifiers = json.loads(pid_file.read_text())
        assert all(alive(identifier) for identifier in identifiers)
        process.kill()
        process.wait(timeout=5)
        deadline = time.monotonic() + 5
        while any(alive(identifier) for identifier in identifiers) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not any(alive(identifier) for identifier in identifiers)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        for identifier in identifiers:
            if alive(identifier):
                os.kill(identifier, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)


def test_watchdog_eof_kills_only_its_owned_group(monkeypatch):
    from types import SimpleNamespace
    from src.ai_workflow import session_watchdog
    killed, closed = [], []
    monkeypatch.setattr(session_watchdog, "sys", SimpleNamespace(argv=["watchdog", "321", "11"]))
    monkeypatch.setattr(session_watchdog, "signal", SimpleNamespace(SIGKILL=9))
    monkeypatch.setattr(session_watchdog, "os", SimpleNamespace(write=lambda *args: None, read=lambda *args: b"",
                        killpg=lambda group, signal: killed.append((group, signal)), close=closed.append))
    session_watchdog.main()
    assert killed == [(321, 9)]
    assert closed == [11]


def test_watchdog_startup_deadline_is_reported_as_budget_timeout(monkeypatch):
    from types import SimpleNamespace
    import select
    from src.ai_workflow import process_supervisor as supervisor
    watcher = SimpleNamespace(stdout=object(), wait=lambda **kwargs: None)
    fake_subprocess = SimpleNamespace(Popen=lambda *a, **k: watcher, DEVNULL=-3, PIPE=-1, TimeoutExpired=subprocess.TimeoutExpired)
    monkeypatch.setattr(supervisor, "subprocess", fake_subprocess)
    monkeypatch.setattr(supervisor, "os", SimpleNamespace(name="posix", pipe=lambda: (11, 12), killpg=lambda *a: None, close=lambda *a: None))
    monkeypatch.setattr(supervisor, "sys", SimpleNamespace(executable="python"))
    monkeypatch.setattr(supervisor, "signal", SimpleNamespace(SIGKILL=9))
    monkeypatch.setattr(supervisor, "time", SimpleNamespace(monotonic=lambda: 20))
    monkeypatch.setattr(select, "select", lambda *a: ([], [], []))
    with pytest.raises(subprocess.TimeoutExpired):
        supervisor.ProcessTree(SimpleNamespace(pid=321, args=["worker"]), 10, {})
