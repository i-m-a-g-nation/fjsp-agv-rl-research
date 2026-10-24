"""Bounded selector experiments; not an OS security sandbox for hostile code."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

from src.data.instance import create_toy_instance
from src.data.loader import load_benchmark_file
from src.scheduling.encoding import ScheduleRecord, ScheduleResult
from src.scheduling.feasibility import check_feasibility
from src.solvers.dispatching import dispatch_eft_solve, dispatch_fifo_solve, dispatch_mwkr_solve, dispatch_spt_solve


_BUILTINS = {name: value for name, value in (
    ("min", min), ("max", max), ("sum", sum), ("len", len), ("abs", abs),
    ("round", round), ("sorted", sorted), ("enumerate", enumerate), ("range", range),
    ("tuple", tuple), ("list", list), ("dict", dict), ("set", set),
    ("float", float), ("int", int), ("bool", bool),
    ("ValueError", ValueError), ("RuntimeError", RuntimeError),
)}


@dataclass(frozen=True)
class SandboxEvaluationResult:
    passed: bool
    error_message: str
    avg_makespan: float
    baseline_eft_makespan: float
    baseline_fifo_makespan: float
    baseline_spt_makespan: float
    baseline_mwkr_makespan: float
    per_instance_makespans: dict[str, int]
    execution_status: str = "failed"
    resource_limits_applied: bool = False
    performance_status: str = "not_evaluated"


def validate_generated_code_ast(code: str, expected_fn_name: str = "ai_select_candidate") -> None:
    if len(code) > 20000:
        raise ValueError("Disallowed generated code size: limit is 20000 characters")
    try:
        tree = ast.parse(code)
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Generated code has syntax error or excessive nesting") from exc
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    if expected_fn_name not in functions:
        raise ValueError(f"Generated code must define a function named `{expected_fn_name}`")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Disallowed import in generated rule")
        if isinstance(node, (ast.While, ast.ClassDef, ast.AsyncFunctionDef, ast.Global, ast.Nonlocal,
                             ast.With, ast.AsyncWith, ast.Delete, ast.Yield, ast.YieldFrom)):
            raise ValueError(f"Disallowed construct: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or not isinstance(node.ctx, ast.Load)):
            raise ValueError("Disallowed attribute access or mutation")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in {*_BUILTINS, *functions}:
                raise ValueError("Disallowed builtin call or method call")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.returns or
                any(default is not None and not isinstance(default, ast.Constant)
                    for default in (*node.args.defaults, *node.args.kw_defaults)) or
                any(arg.annotation for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs))):
            raise ValueError("Disallowed function decorations, defaults, or annotations")
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("Disallowed top-level statements")


def compile_select_fn(code: str, expected_fn_name: str = "ai_select_candidate") -> Callable:
    """Worker-only compilation after resource limits; never run in the graph process."""
    validate_generated_code_ast(code, expected_fn_name)
    namespace: dict = {"__builtins__": _BUILTINS.copy()}
    exec(compile(code, "<generated-selector>", "exec"), namespace)
    return namespace[expected_fn_name]


def _failure(message: str, status: str = "failed") -> SandboxEvaluationResult:
    return SandboxEvaluationResult(False, message[:1000], float("inf"), 0.0, 0.0, 0.0, 0.0, {}, status)


def evaluate_generated_rule(
    code: str, benchmark_paths: list[Path] | None = None, *,
    timeout_seconds: float = 10.0, memory_limit_mb: int = 2048,
) -> SandboxEvaluationResult:
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120:
        raise ValueError("timeout_seconds must be finite and in (0, 120]")
    if type(memory_limit_mb) is not int or not 256 <= memory_limit_mb <= 4096:
        raise ValueError("memory_limit_mb must be an integer in [256, 4096]")
    try:
        validate_generated_code_ast(code)
        instances = [("toy_3x3", create_toy_instance())]
        for path in benchmark_paths or []:
            if not path.is_file():
                return _failure(f"Required benchmark missing: {path.name}")
            if path.stem in {name for name, _ in instances}:
                return _failure(f"Duplicate benchmark name: {path.stem}")
            instances.append((path.stem, load_benchmark_file(path)))
    except Exception as exc:
        return _failure(str(exc))

    payload = {"code": code, "memory_limit_mb": memory_limit_mb, "instances": [
        {"name": name, "num_machines": inst.num_machines,
         "jobs": [[list(op.machine_options) for op in job.operations] for job in inst.jobs]}
        for name, inst in instances
    ]}
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "COMSPEC"}
                   or key.startswith("COVERAGE_")}
    environment.update(PYTHONIOENCODING="utf-8", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    worker = Path(__file__).with_name("sandbox_worker.py")
    try:
        process = subprocess.run(
            [sys.executable, "-I", str(worker)], input=json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8", timeout=timeout_seconds,
            env=environment, cwd=worker.parents[2],
        )
    except subprocess.TimeoutExpired:
        return _failure(f"Selector worker exceeded {timeout_seconds:g}s deadline", "timeout")
    except OSError as exc:
        return _failure(f"Cannot start selector worker: {exc}")
    if process.returncode:
        return _failure(f"Selector worker exited with code {process.returncode}")

    try:
        response = json.loads(process.stdout)
        if response.get("error"):
            return _failure(f"Runtime error during simulation: {response['error']}")
        scores: dict[str, int] = {}
        baselines: dict[str, list[int]] = {key: [] for key in ("eft", "fifo", "spt", "mwkr")}
        if set(response["schedules"]) != {name for name, _ in instances}:
            return _failure("Worker did not return every configured benchmark")
        for name, inst in instances:
            raw = response["schedules"][name]
            result = ScheduleResult(instance=inst, makespan=raw["makespan"],
                                    records=[ScheduleRecord(**item) for item in raw["records"]])
            feasible, violations = check_feasibility(result)
            if not feasible:
                return _failure(f"Infeasible worker schedule on {name}: {violations}")
            scores[name] = result.makespan
            for key, solver in (("eft", dispatch_eft_solve), ("fifo", dispatch_fifo_solve),
                                ("spt", dispatch_spt_solve), ("mwkr", dispatch_mwkr_solve)):
                baselines[key].append(solver(inst).makespan)
        means = {key: sum(values) / len(instances) for key, values in baselines.items()}
        average = sum(scores.values()) / len(instances)
        limited = response.get("resource_limits_applied") is True
        if not limited:
            return _failure("Worker resource limits were not applied")
        return SandboxEvaluationResult(
            True, "", average, means["eft"], means["fifo"], means["spt"], means["mwkr"],
            scores, "completed", limited,
            "better_on_evaluated_instances" if average < min(means.values()) else "not_better_on_evaluated_instances",
        )
    except Exception as exc:
        return _failure(f"Invalid worker result: {exc}")
