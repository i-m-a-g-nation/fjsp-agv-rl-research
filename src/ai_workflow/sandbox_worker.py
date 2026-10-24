"""Private worker. Limits contain resource exhaustion, not hostile OS access."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ai_workflow.sandbox import compile_select_fn
from src.data.instance import FJSPInstance
from src.solvers.dispatching import _dispatch_solve


_job_handle = None


def apply_memory_limit(limit_mb: int) -> None:
    global _job_handle
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limit_mb * 1024**2, limit_mb * 1024**2))
        return
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                    ("max_ws", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    _job_handle = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x100 | 0x2000
    limits.process_memory = limit_mb * 1024**2
    if not _job_handle or not kernel.SetInformationJobObject(_job_handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise OSError("Cannot configure worker memory limit")
    if not kernel.AssignProcessToJobObject(_job_handle, kernel.GetCurrentProcess()):
        raise OSError("Cannot attach worker memory limit")


@dataclass(frozen=True)
class ReadOnlyInstance:
    num_jobs: int
    num_machines: int
    jobs: tuple


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        apply_memory_limit(payload["memory_limit_mb"])
        selector = compile_select_fn(payload["code"])
        schedules = {}
        for item in payload["instances"]:
            instance = FJSPInstance.from_jobs_array(item["jobs"], num_machines=item["num_machines"])
            view = ReadOnlyInstance(instance.num_jobs, instance.num_machines, tuple(instance.jobs))

            def select(candidates, _instance, _rng):
                selected = selector(tuple(candidates), view, None)
                if not isinstance(selected, tuple) or selected not in candidates:
                    raise ValueError("Selector must return one existing candidate")
                return selected

            result = _dispatch_solve(instance, select)
            schedules[item["name"]] = {"makespan": result.makespan, "records": [asdict(r) for r in result.records]}
        print(json.dumps({"schedules": schedules, "resource_limits_applied": True}))
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:800]}"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
