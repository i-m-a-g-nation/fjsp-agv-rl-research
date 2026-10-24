from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph + FAISS RAG automated literature-to-code research workflow."
    )
    parser.add_argument(
        "--paper-path",
        type=Path,
        default=PROJECT_ROOT / "notes" / "papers" / "2023_fjsp_dual_attention_rl.md",
        help="Path to a paper PDF or Markdown file (if stub, auto-fetches arXiv PDF / DOI abstract).",
    )
    parser.add_argument(
        "--goal",
        type=str,
        default="提取车间调度与AGV物流/设备维护协同的数学模型、强化学习状态奖励机制，并对齐到当前项目接口生成可执行派工算子。",
        help="Research goal for the workflow.",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "ai_memory" / "exp_018_ai_rag_workflow_report.md",
        help="Output Markdown report path.",
    )
    parser.add_argument(
        "--rag-index-dir",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "ai_memory" / "rag_index",
        help="Directory to persist the FAISS index and chunk metadata.",
    )
    parser.add_argument(
        "--no-network-fetch",
        action="store_true",
        help="Disable automatic online arXiv PDF / DOI abstract fetching for metadata stubs.",
    )
    parser.add_argument(
        "--strict-require-fulltext",
        action="store_true",
        help="Raise an error if the paper only has metadata/abstract and full PDF could not be obtained.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = LLMConfig()

    print("==> Step 1: Building local FAISS RAG knowledge base from workspace...")
    rag_store = ResearchRAGStore(project_root=PROJECT_ROOT, config=config)
    extra_files = [args.paper_path] if args.paper_path.exists() else []
    num_chunks = rag_store.build_from_workspace(extra_paths=extra_files)
    print(f"    Indexed {num_chunks} workspace chunks.")

    paper_text = ""
    paper_title = args.paper_path.stem
    if args.paper_path.exists():
        paper_text = rag_store._read_file_text(args.paper_path)

    print("==> Step 2: Resolving paper content (Auto-detecting metadata stubs & fetching arXiv PDF / DOI)...")
    workflow = build_research_workflow(rag_store=rag_store, config=config)
    final_state = workflow.invoke(
        {
            "research_goal": args.goal,
            "paper_path": str(args.paper_path),
            "paper_title": paper_title,
            "paper_text": paper_text,
            "allow_network_fetch": not args.no_network_fetch,
            "strict_require_fulltext": args.strict_require_fulltext,
            "max_iterations": 2,
        }
    )

    for log_line in final_state.get("resolution_log", []):
        print(f"    [PaperFetcher] {log_line}")
    print(f"    [ContentDepth] {final_state.get('content_depth', 'unknown')}")

    # Save updated RAG store (including newly downloaded PDF chunks and episodic memory)
    rag_store.save(args.rag_index_dir)
    print(f"    Total RAG chunks persisted: {len(rag_store.chunks)} -> {args.rag_index_dir}")

    report_md = final_state.get("final_summary_markdown", "")
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report_md, encoding="utf-8")

    passed = final_state.get("eval_passed", False)
    metrics = final_state.get("eval_metrics", {})
    print(f"==> Step 3: Sandbox Feasibility Check: {'PASS' if passed else 'FAIL'}")
    print(f"    AI Composite Rule Avg Makespan: {metrics.get('avg_makespan', 0.0):.2f}")
    print(f"    Baseline FIFO Avg Makespan    : {metrics.get('baseline_fifo_makespan', 0.0):.2f}")
    print(f"    Baseline MWKR Avg Makespan    : {metrics.get('baseline_mwkr_makespan', 0.0):.2f}")
    print(f"    Baseline SPT Avg Makespan     : {metrics.get('baseline_spt_makespan', 0.0):.2f}")
    print(f"    Baseline EFT Avg Makespan     : {metrics.get('baseline_eft_makespan', 0.0):.2f}")
    print(f"    Report saved to: {args.output_report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
