from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import random
from typing import Callable, List, Tuple

from src.data.instance import FJSPInstance, create_toy_instance
from src.data.loader import load_benchmark_file
from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility
from src.solvers.dispatching import (
    _dispatch_solve,
    dispatch_eft_solve,
    dispatch_fifo_solve,
    dispatch_mwkr_solve,
    dispatch_spt_solve,
)

_Candidate = Tuple[int, int, int, int, int, int, int]
_SelectFn = Callable[[List[_Candidate], FJSPInstance, random.Random | None], _Candidate]

_FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "open",
    "__import__",
    "compile",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "delattr",
}


@dataclass(frozen=True)
class SandboxEvaluationResult:
    """Result of compiling and benchmarking an AI-generated dispatching rule."""

    passed: bool
    error_message: str
    avg_makespan: float
    baseline_eft_makespan: float
    baseline_fifo_makespan: float
    baseline_spt_makespan: float
    baseline_mwkr_makespan: float
    per_instance_makespans: dict[str, int]


def validate_generated_code_ast(code: str, expected_fn_name: str = "ai_select_candidate") -> None:
    """Ensure generated Python code defines `expected_fn_name` and has no unsafe imports/calls."""

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Generated code has syntax error: {exc}") from exc

    found_fn = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg not in {"math", "random", "typing"}:
                    raise ValueError(f"Disallowed import in generated rule: {alias.name}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALLS:
                raise ValueError(f"Disallowed builtin call in generated rule: {node.func.id}")
        elif isinstance(node, ast.FunctionDef) and node.name == expected_fn_name:
            found_fn = True

    if not found_fn:
        raise ValueError(
            f"Generated code must define a function named `{expected_fn_name}(candidates, instance, rng)`"
        )


def compile_select_fn(
    code: str,
    expected_fn_name: str = "ai_select_candidate",
) -> _SelectFn:
    """Safely compile generated Python code and extract the candidate selection function."""

    validate_generated_code_ast(code, expected_fn_name=expected_fn_name)
    import math

    safe_globals = {
        "__builtins__": {
            "min": min,
            "max": max,
            "sum": sum,
            "len": len,
            "abs": abs,
            "round": round,
            "sorted": sorted,
            "enumerate": enumerate,
            "range": range,
            "tuple": tuple,
            "list": list,
            "dict": dict,
            "set": set,
            "float": float,
            "int": int,
            "bool": bool,
            "ValueError": ValueError,
            "RuntimeError": RuntimeError,
        },
        "math": math,
        "random": random,
    }
    local_ns: dict[str, object] = {}
    exec(compile(code, "<ai_generated_rule>", "exec"), safe_globals, local_ns)  # noqa: S102
    fn = local_ns.get(expected_fn_name)
    if not callable(fn):
        raise ValueError(f"Function `{expected_fn_name}` is not callable")
    return fn  # type: ignore[return-value]


def evaluate_generated_rule(
    code: str,
    benchmark_paths: list[Path] | None = None,
) -> SandboxEvaluationResult:
    """Execute the generated dispatching rule against benchmark instances and check feasibility."""

    try:
        select_fn = compile_select_fn(code)
    except Exception as exc:
        return SandboxEvaluationResult(
            passed=False,
            error_message=str(exc),
            avg_makespan=float("inf"),
            baseline_eft_makespan=0.0,
            baseline_fifo_makespan=0.0,
            baseline_spt_makespan=0.0,
            baseline_mwkr_makespan=0.0,
            per_instance_makespans={},
        )

    instances: list[tuple[str, FJSPInstance]] = [("toy_3x3", create_toy_instance())]
    if benchmark_paths:
        for path in benchmark_paths:
            if path.exists():
                instances.append((path.stem, load_benchmark_file(path)))

    ai_makespans: dict[str, int] = {}
    eft_scores: list[int] = []
    fifo_scores: list[int] = []
    spt_scores: list[int] = []
    mwkr_scores: list[int] = []

    try:
        for name, inst in instances:
            result: ScheduleResult = _dispatch_solve(inst, select_fn, rng=random.Random(42))
            feasible, violations = check_feasibility(result)
            if not feasible:
                return SandboxEvaluationResult(
                    passed=False,
                    error_message=f"Infeasible schedule on {name}: {violations}",
                    avg_makespan=float("inf"),
                    baseline_eft_makespan=0.0,
                    baseline_fifo_makespan=0.0,
                    baseline_spt_makespan=0.0,
                    baseline_mwkr_makespan=0.0,
                    per_instance_makespans={},
                )
            if result not in candidates_check(result):
                pass
            ai_makespans[name] = result.makespan
            eft_scores.append(dispatch_eft_solve(inst).makespan)
            fifo_scores.append(dispatch_fifo_solve(inst).makespan)
            spt_scores.append(dispatch_spt_solve(inst).makespan)
            mwkr_scores.append(dispatch_mwkr_solve(inst).makespan)
    except Exception as exc:
        return SandboxEvaluationResult(
            passed=False,
            error_message=f"Runtime error during simulation: {exc}",
            avg_makespan=float("inf"),
            baseline_eft_makespan=0.0,
            baseline_fifo_makespan=0.0,
            baseline_spt_makespan=0.0,
            baseline_mwkr_makespan=0.0,
            per_instance_makespans={},
        )

    n = max(1, len(instances))
    return SandboxEvaluationResult(
        passed=True,
        error_message="",
        avg_makespan=sum(ai_makespans.values()) / n,
        baseline_eft_makespan=sum(eft_scores) / n,
        baseline_fifo_makespan=sum(fifo_scores) / n,
        baseline_spt_makespan=sum(spt_scores) / n,
        baseline_mwkr_makespan=sum(mwkr_scores) / n,
        per_instance_makespans=ai_makespans,
    )


def candidates_check(result: ScheduleResult) -> list[ScheduleResult]:
    return [result]
