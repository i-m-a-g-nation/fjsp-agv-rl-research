"""Finite, reproducible dynamic-baseline batches; no AI or optimizer generation."""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

from src.data.loader import load_benchmark_file
from src.dynamic import check_dynamic_feasibility, reschedule_from_state
from src.research.protocol import build_case, instance_path, parse_protocol
from src.scheduling.feasibility import check_feasibility


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encoded(value))


def _prepare(protocol_path, project_root):
    raw = Path(protocol_path).read_bytes()
    protocol = parse_protocol(raw, project_root)
    inputs = []
    for item in protocol.instances:
        path = instance_path(project_root, item.path)
        known_root = Path(__file__).resolve().parents[2] / "instances" / "fjsplib"
        index_base = 1 if path.resolve().is_relative_to(known_root.resolve()) else "auto"
        try:
            data, error = path.read_bytes(), ""
        except OSError as exc:
            data, error = None, f"{type(exc).__name__}: {exc}"
        inputs.append({"id": item.id, "path": str(path), "relative_path": item.path,
                       "sha256": _hash(data) if data is not None else None, "data": data, "error": error,
                       "machine_index_base": index_base})
    return protocol, raw, inputs


def describe_protocol(protocol_path: Path, project_root: Path) -> dict:
    protocol, raw, inputs = _prepare(protocol_path, project_root)
    return {"protocol": protocol.model_dump(mode="json"), "protocol_hash": _hash(raw),
            "expected_runs": protocol.expected_runs,
            "case_count": len(protocol.instances) * len(protocol.event_types) * len(protocol.seeds),
            "inputs": [{key: value for key, value in item.items() if key != "data"} for item in inputs]}


def _records(result):
    return [asdict(record) for record in sorted(result.records, key=lambda r: (r.job_id, r.op_id, r.machine_id, r.start))]


def _diagnostic_value(value, depth=0):
    """Bound malformed diagnostics; never use this to certify or hash a schedule."""
    if depth > 12:
        return "diagnostic_depth_limit"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, float):
        return value if math.isfinite(value) else f"nonfinite:{value}"
    if isinstance(value, dict):
        return {str(key)[:100]: _diagnostic_value(item, depth + 1) for key, item in list(value.items())[:1000]}
    if isinstance(value, (tuple, list)):
        return [_diagnostic_value(item, depth + 1) for item in value[:10000]]
    return f"unserializable:{type(value).__name__}"


def _diagnostic_records(result):
    if result is None:
        return [], ""
    try:
        return _diagnostic_value(_records(result)), ""
    except Exception as exc:
        return [], f"{type(exc).__name__}: {str(exc)[:500]}"


def _case_data(case):
    instance = case.state.instance
    return {"event": case.event_spec, "initial_records": _records(case.initial),
            "initial_makespan": case.initial.makespan, "frozen_records": [asdict(r) for r in case.frozen],
            "state": {"jobs": [[list(op.machine_options) for op in job.operations] for job in instance.jobs],
                      "num_machines": instance.num_machines, "current_time": case.state.current_time,
                      "job_release_times": case.state.job_release_times,
                      "machine_unavailable_until": case.state.machine_unavailable_until}}


def _runtime_metadata():
    root = Path(__file__).resolve().parents[2]
    paths = [*sorted((root / "src").rglob("*.py")), root / "pyproject.toml"]
    source_hashes = {path.relative_to(root).as_posix(): _hash(path.read_bytes()) for path in paths}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False).stdout.strip()
    return {"python": sys.version, "platform": platform.platform(), "git_head": revision,
            "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pydantic", "matplotlib")},
            "source_hashes": source_hashes, "source_digest": _hash(_encoded(source_hashes))}


def _aggregate(rows, repetitions):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["case_id"], row["rule"])].append(row)
    result = []
    for (case_id, rule), members in groups.items():
        passed = [row for row in members if row["feasible"]]
        hashes = {row["schedule_hash"] for row in passed}
        durations = [row["runtime_s"] for row in passed]
        result.append({"case_id": case_id, "rule": rule, "expected_runs": repetitions,
                       "passed_runs": len(passed), "failed_runs": len(members) - len(passed),
                       "reproducible": len(passed) == repetitions and len(hashes) == 1,
                       "makespan": passed[0]["makespan"] if len(hashes) == 1 else None,
                       "runtime_median_s": statistics.median(durations) if durations else None,
                       "runtime_min_s": min(durations) if durations else None,
                       "runtime_max_s": max(durations) if durations else None})
    return result


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _report(manifest):
    lines = ["<!-- fjsp-generated-report track=foundation -->", "# Phase 2A Fixed Baseline Report", "",
             f"Protocol: `{manifest['protocol_id']}` / `{manifest['protocol_hash']}`.",
             f"Status: **{manifest['status']}**. Passed {manifest['passed_runs']}/{manifest['expected_runs']} runs; failed {manifest['failed_runs']}.",
             f"Declared instance/event/seed configurations: {manifest['case_count']}; distinct case snapshots: {manifest['unique_case_count']}.",
             f"Complete groups with inconsistent repeated schedules: {manifest['nonreproducible_groups']}. Neither seeds nor timing repetitions establish independent statistical samples.",
             "", "| Case | Rule | PASS/expected | Makespan | Repeatable schedule | Median runtime (s) |",
             "|---|---|---:|---:|---|---:|"]
    for group in manifest["groups"]:
        runtime = "" if group["runtime_median_s"] is None else f"{group['runtime_median_s']:.6f}"
        makespan = "" if group["makespan"] is None else str(group["makespan"])
        lines.append(f"| {group['case_id']} | {group['rule']} | {group['passed_runs']}/{group['expected_runs']} | {makespan} | {group['reproducible']} | {runtime} |")
    lines.extend(["", "## Interpretation limits", "",
                  "PASS requires the existing static and dynamic feasibility checkers. Failures remain in raw.csv, cases and schedule artifacts.",
                  "Runtime includes the existing rescheduler's internal checks, excludes input preparation, plotting and the additional outer checks; hardware and load affect timing.",
                  "Each case is an independent single perturbation of the same FIFO initial schedule; these are not continuous online simulations.",
                  "Breakdown starts only when the selected machine is idle; no preemption or preventive-maintenance optimization is represented.",
                  "No dynamic optimality or statistical superiority is established. No static CP-SAT/BKS gap is used for the modified problem.",
                  "This run is baseline validation, not human scientific acceptance. Innovation and graduation research goals remain NOT ACHIEVED.",
                  "Representative plots are first-seed, first-repeat EFT schedules, not selected by best performance.", ""])
    if manifest["plot_errors"]:
        lines.append(f"Plot failures: {len(manifest['plot_errors'])}; see manifest.json.")
    return "\n".join(lines)


def run_protocol(protocol_path: Path, output_dir: Path, project_root: Path, *,
                 expected_protocol_hash: str | None = None, expected_input_hashes: dict | None = None,
                 plots: bool = True) -> dict:
    protocol, raw, inputs = _prepare(protocol_path, project_root)
    digest = _hash(raw)
    input_hashes = {item["path"]: item["sha256"] for item in inputs}
    if expected_protocol_hash is not None and expected_protocol_hash != digest:
        raise ValueError("Reviewed protocol changed")
    if expected_input_hashes is not None and input_hashes != expected_input_hashes:
        raise ValueError("Reviewed input changed")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "protocol.json").write_bytes(raw)
    for name in ("inputs", "cases", "schedules", "gantt"):
        (output_dir / name).mkdir()
    rows, plot_errors, case_hashes = [], [], {}
    manifest = {"protocol_id": protocol.protocol_id, "protocol_hash": digest, "status": "RUNNING",
                "expected_runs": protocol.expected_runs, "case_count": len(inputs) * len(protocol.event_types) * len(protocol.seeds),
                "input_hashes": {item["id"]: item["sha256"] for item in inputs},
                "input_index_bases": {item["id"]: item["machine_index_base"] for item in inputs}, "runtime": _runtime_metadata()}
    _write_json(output_dir / "manifest.json", manifest)
    for item in inputs:
        snapshot = output_dir / "inputs" / f"{item['id']}.fjs"
        if item["data"] is not None:
            snapshot.write_bytes(item["data"])
        for event_type in protocol.event_types:
            for seed in protocol.seeds:
                case_id = f"{item['id']}-{event_type}-{seed}"
                case, case_error = None, item["error"]
                try:
                    if case_error:
                        raise ValueError(case_error)
                    case = build_case(load_benchmark_file(snapshot, machine_index_base=item["machine_index_base"]), event_type, seed)
                    case_data = _case_data(case)
                    case_hashes[case_id] = _hash(_encoded(case_data))
                    _write_json(output_dir / "cases" / f"{case_id}.json", case_data)
                except Exception as exc:
                    case_error = f"case: {type(exc).__name__}: {exc}"
                    _write_json(output_dir / "cases" / f"{case_id}.json", {"error": case_error})
                for rule in protocol.rules:
                    for repeat in range(protocol.timing_repetitions):
                        result, error, accepted, schedule_hash = None, case_error, False, None
                        runtime_s = 0.0
                        if case is not None:
                            started = time.perf_counter()
                            try:
                                result = reschedule_from_state(case.state, case.frozen, rule=rule)
                                runtime_s = time.perf_counter() - started
                                if result.instance != case.state.instance:
                                    raise ValueError("Result does not reference the case instance")
                                static_ok, static_issues = check_feasibility(result)
                                dynamic_ok, dynamic_issues = check_dynamic_feasibility(result, case.state, case.frozen)
                                accepted = static_ok and dynamic_ok
                                error = "" if accepted else f"static={static_issues}; dynamic={dynamic_issues}"
                                if accepted:
                                    schedule_hash = _hash(_encoded({"records": _records(result), "makespan": result.makespan}))
                            except Exception as exc:
                                runtime_s = time.perf_counter() - started
                                accepted, schedule_hash = False, None
                                error = f"run: {type(exc).__name__}: {str(exc)[:500]}"
                        run_id = f"{case_id}-{rule}-{repeat}"
                        row = {"case_id": case_id, "instance_id": item["id"], "event_type": event_type, "seed": seed,
                               "rule": rule, "repeat": repeat, "feasible": accepted,
                               "makespan": result.makespan if accepted else None, "runtime_s": runtime_s,
                               "schedule_hash": schedule_hash, "error": error}
                        rows.append(row)
                        diagnostic_records, serialization_error = (_records(result), "") if accepted else _diagnostic_records(result)
                        _write_json(output_dir / "schedules" / f"{run_id}.json",
                                    {**row, "records": diagnostic_records, "diagnostic_only": not accepted,
                                     "record_serialization_error": serialization_error})
                        if plots and accepted and rule == "eft" and seed == protocol.seeds[0] and repeat == 0:
                            try:
                                from src.vis.gantt import plot_gantt
                                plot_gantt(result, title=f"{case_id} / EFT", save_path=output_dir / "gantt" / f"{case_id}-eft.png")
                            except Exception as exc:
                                plot_errors.append({"case_id": case_id, "error": f"{type(exc).__name__}: {exc}"})
    groups = _aggregate(rows, protocol.timing_repetitions)
    passed = sum(row["feasible"] for row in rows)
    manifest.update(passed_runs=passed, failed_runs=len(rows) - passed, groups=groups, plot_errors=plot_errors,
                    case_hashes=case_hashes, unique_case_count=len(set(case_hashes.values())),
                    nonreproducible_groups=sum(g["passed_runs"] == g["expected_runs"] and not g["reproducible"] for g in groups),
                    status="COMPLETED" if passed == protocol.expected_runs and all(g["reproducible"] for g in groups) and not plot_errors else "FAILED",
                    deterministic_digest=_hash(_encoded({"protocol_hash": digest, "inputs": manifest["input_hashes"], "cases": case_hashes,
                        "runs": [{key: value for key, value in row.items() if key != "runtime_s"} for row in rows]})))
    _write_csv(output_dir / "raw.csv", rows)
    _write_csv(output_dir / "aggregate.csv", groups)
    (output_dir / "report.md").write_text(_report(manifest), encoding="utf-8")
    manifest["artifacts"] = {p.relative_to(output_dir).as_posix(): _hash(p.read_bytes())
                             for p in sorted(output_dir.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def verify_batch_artifacts(output_dir: Path, expected_manifest_hash: str) -> None:
    output_dir = Path(output_dir)
    raw = (output_dir / "manifest.json").read_bytes()
    if _hash(raw) != expected_manifest_hash:
        raise ValueError("Reviewed batch manifest changed")
    for relative, expected in json.loads(raw)["artifacts"].items():
        path = (output_dir / relative).resolve()
        if not path.is_relative_to(output_dir.resolve()) or _hash(path.read_bytes()) != expected:
            raise ValueError("Reviewed batch artifact changed")
