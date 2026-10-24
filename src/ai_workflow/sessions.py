"""Local checkpoint sessions with content-bound human decisions and budgets."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, fields
import hashlib
import importlib.metadata
import json
from pathlib import Path
import os
import subprocess
import time
import sys

from src.ai_workflow.config import LLMConfig, default_project_root
from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.process_supervisor import supervised_json_process
from src.ai_workflow.review import artifact_hash, json_safe, validate_review_decision
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget


def _write_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(json_safe(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def _session_lock(folder):
    with (folder / "session.lock").open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Session is already running in another process") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _config_values(config):
    return {item.name: getattr(config, item.name) for item in fields(config) if item.name not in {"api_key", "budget"}}


def _code_hash():
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for path in [*sorted((root / "src").rglob("*.py")), root / "pyproject.toml"]:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def read_session_status(session_dir: Path) -> dict:
    folder = Path(session_dir)
    result = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    if (folder / "session.sqlite").exists():
        result["budget"] = RunBudget.read_snapshot(folder / "session.sqlite")
    return result


def _runtime_versions():
    return {"python": sys.version, **{name: importlib.metadata.version(name) for name in
            ("langgraph", "langgraph-checkpoint-sqlite", "faiss-cpu", "pypdf", "numpy", "ortools")}}


def _benchmark_hashes(paths):
    return {str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None for path in paths}


def run_session(
    session_dir: Path, *, track: str, config: LLMConfig, input_state: dict | None = None,
    project_root: Path | None = None, benchmark_paths: list[Path] | None = None,
    limits: BudgetLimits | None = None, decision: dict | None = None,
) -> dict:
    folder = Path(session_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    contract = get_research_contract(track)
    config_hash = artifact_hash({**_config_values(config), "live": config.has_api_key})
    with _session_lock(folder):
        spec_path = folder / "session.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            if spec["track"] != track:
                raise ValueError("Session track cannot change on resume")
            if spec["config_hash"] != config_hash or spec["code_hash"] != _code_hash() or spec["contract_hash"] != contract.contract_hash:
                raise ValueError("Session configuration, code, or contract changed; create a new session")
            if project_root is not None and str(project_root.resolve()) != spec["project_root"]:
                raise ValueError("Session workspace cannot change on resume")
            if benchmark_paths is not None and [str(p.resolve()) for p in benchmark_paths] != spec["benchmark_paths"]:
                raise ValueError("Session benchmark set cannot change on resume")
            if _benchmark_hashes(spec["benchmark_paths"]) != spec["benchmark_hashes"]:
                raise ValueError("Session benchmark contents changed; create a new session")
            if _runtime_versions() != spec["runtime_versions"]:
                raise ValueError("Session runtime configuration changed; create a new session")
            if input_state is not None and artifact_hash(input_state) != artifact_hash(spec["input_state"]):
                raise ValueError("Session input cannot change on resume")
            status = read_session_status(folder)
            if status["status"] != "WAITING_HUMAN":
                raise ValueError("Session is terminal or interrupted; inspect it and create a new session")
            if decision is None:
                return status
            decision = validate_review_decision(status["pending_review"], decision)
            stored_limits = BudgetLimits(**spec["limits"])
            if limits is not None and asdict(limits) != asdict(stored_limits):
                raise ValueError("Cannot change budget limits on resume")
            limits = stored_limits
        else:
            if any((folder / name).exists() for name in ("rag_index", "session.sqlite", "status.json")):
                raise ValueError("Unexpected session artifacts without associated session metadata")
            if input_state is None or decision is not None:
                raise ValueError("New session requires input and cannot start with a review decision")
            allowed = {"paper_path", "paper_text", "paper_title", "research_goal", "allow_network_fetch", "strict_require_fulltext", "max_iterations", "requested_capabilities"}
            if set(input_state) - allowed:
                raise ValueError("Unexpected initial session fields")
            limits = limits or BudgetLimits()
            root = (project_root or default_project_root()).resolve()
            selected_benchmarks = benchmark_paths if benchmark_paths is not None else [
                root / "instances/fjsplib/Brandimarte1993/mk01.fjs", root / "instances/fjsplib/KacemHammadiBorne2002/kacem1.fjs",
                root / "instances/fjsplib/FattahiMehrabadJolai2007/fattahi1.fjs"]
            selected_benchmarks = [str(p.resolve()) for p in selected_benchmarks]
            spec = {"track": track, "project_root": str((project_root or default_project_root()).resolve()),
                    "input_state": input_state, "contract_hash": contract.contract_hash,
                    "config_hash": config_hash, "code_hash": _code_hash(), "limits": asdict(limits),
                    "benchmark_paths": selected_benchmarks, "benchmark_hashes": _benchmark_hashes(selected_benchmarks),
                    "runtime_versions": _runtime_versions(), "seed": 42}
            _write_json(spec_path, spec)
        budget = RunBudget(folder / "session.sqlite", limits)
        _write_json(folder / "status.json", {"status": "RUNNING", "track": track, "budget": budget.snapshot()})
        started = time.monotonic()
        segment = None
        try:
            segment, remaining = budget.reserve_active_segment()
            result = supervised_json_process(Path(__file__).with_name("session_worker.py"),
                                             {"folder": str(folder), "spec": spec,
                                              "config": {**_config_values(config), "api_key": config.api_key},
                                              "decision": decision, "segment_id": segment}, remaining)
        except (subprocess.TimeoutExpired, BudgetExceeded):
            result = {"status": "BUDGET_EXHAUSTED", "error": "Active execution time budget exhausted"}
        except Exception as exc:
            result = {"status": "FAILED", "error": f"Worker failure: {type(exc).__name__}"}
        finally:
            if segment is not None:
                budget.finish_active_segment(segment, time.monotonic() - started)
        result.update(track=track, budget=budget.snapshot(), runtime_versions=spec["runtime_versions"], seed=42)
        _write_json(folder / "status.json", result)
        if result.get("pending_review"):
            request = result["pending_review"]
            _write_json(folder / "review-request.json", request)
            _write_json(folder / "decision-template.json", {"stage": request["stage"], "artifact_hash": request["artifact_hash"],
                       "decision": "", "reviewer": "", "note": ""})
        return result
