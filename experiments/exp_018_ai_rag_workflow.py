from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_workflow import LLMConfig
from src.ai_workflow.config import load_dotenv_if_present
from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.review import json_safe
from src.ai_workflow.runtime_budget import BudgetLimits
from src.ai_workflow.sessions import read_session_status, run_session


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persistent supervised research assistant; approvals never certify research completion.")
    parser.add_argument("--track", required=True, choices=("foundation", "innovation", "graduation"))
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--paper-path", type=Path)
    parser.add_argument("--experiment-protocol", type=Path, help="Fixed Phase 2A protocol; bypasses RAG and model/code generation, retaining all three reviews.")
    parser.add_argument('--graduation-request', type=Path, help='Reviewed fixed/joint graduation request; offline references with three review gates.')
    parser.add_argument("--goal")
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--decision-file", type=Path, help="Human-completed content-bound decision JSON.")
    parser.add_argument("--status", action="store_true", help="Read session status without running any node.")
    parser.add_argument("--max-active-seconds", type=float)
    parser.add_argument("--max-provider-calls", type=int)
    parser.add_argument("--max-output-token-budget", type=int)
    parser.add_argument("--output-report", type=Path)
    parser.add_argument("--rag-index-dir", type=Path, help="Optional export of the final index; checkpoints retain their own index.")
    network = parser.add_mutually_exclusive_group()
    network.add_argument("--allow-network-fetch", action="store_true")
    network.add_argument("--no-network-fetch", action="store_false", dest="allow_network_fetch")
    parser.set_defaults(allow_network_fetch=None)
    parser.add_argument("--strict-require-fulltext", action="store_true", default=None)
    parser.add_argument("--allow-fallback", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.status:
        try:
            if args.session_dir is None:
                raise ValueError("--status requires --session-dir")
            print(json.dumps(read_session_status(args.session_dir), ensure_ascii=False, indent=2))
            return 0
        except (ValueError, OSError) as exc:
            print(f"Cannot read session status: {exc}")
            return 1
    if args.decision_file and (args.session_dir is None or not (args.session_dir / "session.json").is_file()):
        print("A review decision requires an existing --session-dir.")
        return 1
    try:
        stored_input = json.loads((args.session_dir / "session.json").read_text(encoding="utf-8"))["input_state"] if args.session_dir and (args.session_dir / "session.json").is_file() else {}
    except (ValueError, OSError) as exc:
        print(f"Cannot read session configuration: {exc}")
        return 1
    protocol_mode = bool(args.experiment_protocol or stored_input.get("experiment_protocol_path"))
    graduation_mode = bool(args.graduation_request or stored_input.get('graduation_request_path'))
    if graduation_mode and (args.track != 'graduation' or protocol_mode):
        print('Graduation request requires graduation track and cannot combine experiment protocol inputs.')
        return 1
    if (protocol_mode or graduation_mode) and (args.mode != "offline" or args.paper_path is not None or args.allow_network_fetch or
                          args.strict_require_fulltext or args.allow_fallback or args.rag_index_dir):
        print("Fixed protocol requires offline mode and cannot combine paper, network, model fallback or RAG export options.")
        return 1
    if args.mode == "live":
        load_dotenv_if_present()
        config = LLMConfig(allow_fallback=args.allow_fallback)
        if not config.has_api_key:
            print("Live mode requires an API key; no provider calls were made.")
            return 1
    else:
        config = LLMConfig(api_key="", embedding_backend="hybrid_local")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = args.session_dir or PROJECT_ROOT / "experiments" / "ai_memory" / args.track / stamp
    output = args.output_report or folder / "report.md"
    try:
        existing = (folder / "session.json").is_file()
        state = None
        if existing:
            frozen_input = json.loads((folder / "session.json").read_text(encoding="utf-8"))["input_state"]
            supplied = {"research_goal": args.goal, "allow_network_fetch": args.allow_network_fetch,
                        "strict_require_fulltext": args.strict_require_fulltext,
                        "paper_path": str(args.paper_path.resolve()) if args.paper_path is not None else None}
            supplied["experiment_protocol_path"] = str(args.experiment_protocol.resolve()) if args.experiment_protocol else None
            supplied['graduation_request_path'] = str(args.graduation_request.resolve()) if args.graduation_request else None
            if any(value is not None and value != frozen_input.get(key) for key, value in supplied.items()):
                raise ValueError("Explicit input override conflicts with the frozen session; create a new session")
        if not existing:
            if graduation_mode:
                state = {'research_goal': args.goal or '', 'graduation_request_path': str(args.graduation_request.resolve()),
                         'allow_network_fetch': False}
            elif protocol_mode:
                state = {"research_goal": args.goal or "", "experiment_protocol_path": str(args.experiment_protocol.resolve()),
                         "allow_network_fetch": False}
            else:
                paper = args.paper_path or PROJECT_ROOT / "notes" / "papers" / "2023_fjsp_dual_attention_rl.md"
                if not paper.is_file():
                    raise ValueError(f"Paper input missing: {paper}")
                state = {"research_goal": args.goal or "", "paper_path": str(paper.resolve()),
                         "paper_title": paper.stem, "paper_text": "",
                         "allow_network_fetch": bool(args.allow_network_fetch),
                         "strict_require_fulltext": bool(args.strict_require_fulltext) or args.mode == "live", "max_iterations": 2}
        budget_args = {"max_active_seconds": args.max_active_seconds, "max_provider_calls": args.max_provider_calls,
                       "max_output_tokens": args.max_output_token_budget}
        overrides = {key: value for key, value in budget_args.items() if value is not None}
        if existing and overrides:
            stored = json.loads((folder / "session.json").read_text(encoding="utf-8"))["limits"]
            limits = BudgetLimits(**{**stored, **overrides})
        else:
            defaults = {'max_provider_calls': 0, 'max_output_tokens': 0} if graduation_mode else {}
            limits = BudgetLimits(**{**defaults, **overrides}) if overrides or not existing else None
        decision = json.loads(args.decision_file.read_text(encoding="utf-8")) if args.decision_file else None
        result = run_session(folder, track=args.track, config=config, input_state=state,
                             project_root=PROJECT_ROOT, limits=limits, decision=decision)
        final = result.get("state", {})
        output.parent.mkdir(parents=True, exist_ok=True)
        metadata = {**final, "contract": get_research_contract(args.track).to_dict(),
                    "session_status": result["status"], "budget": result["budget"],
                    "runtime_versions": result.get("runtime_versions", {}), "seed": result.get("seed", 42)}
        if result["status"] != "COMPLETED":
            metadata["overall_status"] = result["status"]
        output.with_suffix(".json").write_text(json.dumps(json_safe(metadata), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if final.get("final_summary_markdown"):
            text = final["final_summary_markdown"]
            if result["status"] != "COMPLETED":
                text += f"\n\n会话状态：{result['status']}；人工审核尚未完成。\n"
            output.write_text(text, encoding="utf-8")
        if args.rag_index_dir and result["status"] == "COMPLETED":
            args.rag_index_dir.mkdir(parents=True, exist_ok=True)
            for name in ("chunks.json", "index.faiss"):
                source = folder / "rag_index" / name
                if source.exists() and source.resolve() != (args.rag_index_dir / name).resolve():
                    shutil.copy2(source, args.rag_index_dir / name)
    except (ValueError, OSError) as exc:
        print(f"Workflow stopped: {exc}")
        return 1
    print(f"Session: {folder}; status: {result['status']}")
    print(f"Budget: {result['budget']}")
    if result["status"] == "WAITING_HUMAN":
        print(f"Review {result['pending_review']['stage']}: {folder / 'review-request.json'}")
        print(f"Complete {folder / 'decision-template.json'} and resume with --decision-file.")
        return 3
    if result["status"] != "COMPLETED":
        print(result.get("error", "Human rejected this run."))
        return 1
    print(f"Research status: {final['acceptance']['research_status']}; report: {output}")
    if not final.get("eval_passed") or final.get("execution_mode") == "degraded":
        return 1
    return 0 if args.track == "foundation" else 2


if __name__ == "__main__":
    raise SystemExit(main())
