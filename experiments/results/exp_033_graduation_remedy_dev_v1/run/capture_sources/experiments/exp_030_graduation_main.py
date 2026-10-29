"""Prepare/recheck G3A evidence or run only with its content-bound human approval."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ai_workflow.graduation_main_evidence import prepare_main_evidence,recheck_main_evidence,load_scope_context
from src.ai_workflow.graduation_main_backend import run_main,recheck_main_run
from src.ai_workflow.graduation_main_budget import read_main_budget


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare-evidence')
    prep.add_argument('--review-dir',type=Path,required=True)
    prep.add_argument('--output-dir',type=Path,required=True)
    prep.add_argument('--validation-log',type=Path,required=True)
    prep.add_argument('--validation-record',type=Path,required=True)
    check=sub.add_parser('recheck-evidence');check.add_argument('--evidence-dir',type=Path,required=True)
    status=sub.add_parser('status');status.add_argument('--review-dir',type=Path,required=True)
    run=sub.add_parser('run')
    run.add_argument('--review-dir',type=Path,required=True)
    run.add_argument('--evidence-dir',type=Path,required=True)
    run.add_argument('--output-dir',type=Path,required=True)
    replay=sub.add_parser('recheck-run')
    replay.add_argument('--review-dir',type=Path,required=True)
    replay.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='prepare-evidence':
            result=prepare_main_evidence(args.review_dir,args.output_dir,args.validation_log,args.validation_record)
        elif args.action=='recheck-evidence':result=recheck_main_evidence(args.evidence_dir)
        elif args.action=='run':result=run_main(args.review_dir,args.evidence_dir,args.output_dir)
        elif args.action=='recheck-run':result=recheck_main_run(args.output_dir,load_scope_context(args.review_dir)['cases'])
        else:
            context=load_scope_context(args.review_dir)
            result={'state':json.loads((args.review_dir/'state.json').read_text(encoding='utf-8')),
                'budget':read_main_budget(context['scope_dir'])}
    except Exception as exc:
        print(f'Main workflow stopped: {type(exc).__name__}: {exc}')
        return 1
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result.get('status') not in ('FAILED','BUDGET_EXHAUSTED') else 1


if __name__=='__main__':raise SystemExit(main())
