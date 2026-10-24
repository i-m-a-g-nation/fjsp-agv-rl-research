"""Private process entry; credentials arrive over stdin and are never persisted."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# On Linux, stop even during bootstrap if the owning supervisor disappears.
if sys.platform == "linux":
    import ctypes
    import signal
    expected_parent = int(sys.argv[1])
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL) != 0:
        raise SystemExit("Cannot establish supervisor ownership")
    if os.getppid() != expected_parent:
        os.killpg(os.getpgrp(), signal.SIGKILL)

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow
from src.ai_workflow.review import artifact_hash, json_safe, validate_review_decision
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget
from src.ai_workflow.evidence_sources import assert_source_files_unchanged


def _restore_index(folder, store, database):
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS workflow_artifacts (name TEXT PRIMARY KEY, sha256 TEXT NOT NULL)")
        expected = dict(db.execute("SELECT name,sha256 FROM workflow_artifacts"))
    index = folder / "rag_index"
    current = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in index.iterdir() if p.name in {"chunks.json", "index.faiss"}} if index.exists() else {}
    if current != expected:
        raise ValueError("RAG snapshot is not associated with this checkpoint")
    if current:
        restored = ResearchRAGStore.load(index, config=store.config, rebuild_missing_index=False)
        store.chunks, store.index = restored.chunks, restored.index


def _record_index(folder, store, database):
    index = folder / "rag_index"
    store.save(index)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM workflow_artifacts")
        db.executemany("INSERT INTO workflow_artifacts VALUES (?,?)", [(p.name, hashlib.sha256(p.read_bytes()).hexdigest())
                       for p in index.iterdir() if p.name in {"chunks.json", "index.faiss"}])


def main():
    payload = json.loads(sys.stdin.read())
    folder, spec = Path(payload["folder"]), payload["spec"]
    budget = RunBudget(folder / "session.sqlite", BudgetLimits(**spec["limits"]))
    budget.start_segment(payload["segment_id"])
    cfg = LLMConfig(**payload["config"], budget=budget)
    index = folder / "rag_index"
    try:
        store = ResearchRAGStore(Path(spec["project_root"]), cfg)
        context = {"budget": spec["limits"], "mode": "live" if cfg.has_api_key else "offline",
                   "config_hash": spec["config_hash"], "code_hash": spec["code_hash"],
                   "session_spec_hash": artifact_hash(spec), "workspace": spec["project_root"],
                   "benchmark_hashes": spec["benchmark_hashes"], "model_name": cfg.model_name}
        context["protocol_hash"] = spec.get("protocol_hash")
        with SqliteSaver.from_conn_string(str(folder / "session.sqlite")) as saver:
            graph = build_research_workflow(store, cfg,
                    [Path(p) for p in spec["benchmark_paths"]],
                    track=spec["track"], checkpointer=saver, review_required=True,
                    workspace_index_path=index, review_context=context)
            graph_config = {"configurable": {"thread_id": "research-session"}, "recursion_limit": 24}
            snapshot = graph.get_state(graph_config)
            if payload.get("decision"):
                interrupts = [item for task in snapshot.tasks for item in task.interrupts]
                if len(interrupts) != 1 or not snapshot.next:
                    raise ValueError("No pending checkpoint review; stale status cannot resume")
                validate_review_decision(interrupts[0].value, payload["decision"])
                if snapshot.values.get("session_identity") and snapshot.values["session_identity"] != artifact_hash(context):
                    raise ValueError("Checkpoint session identity changed")
                source = snapshot.values.get("paper_path")
                if source and snapshot.values.get("source_file_hash") and hashlib.sha256(Path(source).read_bytes()).hexdigest() != snapshot.values["source_file_hash"]:
                    raise ValueError("Reviewed source changed")
                evidence_source = snapshot.values.get("extraction_report", {}).get("evidence_audit", {}).get("source", {})
                assert_source_files_unchanged(evidence_source)
            _restore_index(folder, store, folder / "session.sqlite")
            value = Command(resume=payload["decision"]) if payload.get("decision") else spec["input_state"]
            state = graph.invoke(value, graph_config)
            pending = state.pop("__interrupt__", ())
        if state.get("content_depth"):
            _record_index(folder, store, folder / "session.sqlite")
        if pending:
            result = {"status": "WAITING_HUMAN", "pending_review": pending[0].value, "state": state}
        else:
            result = {"status": "REJECTED" if state.get("overall_status") == "REJECTED" else "COMPLETED", "state": state}
    except BudgetExceeded as exc:
        result = {"status": "BUDGET_EXHAUSTED", "error": str(exc)}
    except Exception as exc:
        result = {"status": "FAILED", "error": f"Workflow stage failed: {type(exc).__name__}"}
    print(json.dumps(json_safe(result), ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
