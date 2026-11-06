"""Non-executable final evaluation runbook contract. Actual mode always denied."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from scripts.compatibility.handoff_support import ROOT,cfg,read,save,sha,no_data_access
from food_procurement_intelligence.evaluation.final_contract import publication_gate,execution_contract,deny_actual_evaluation


def preflight(candidate:Path,expected_sha:str) -> dict:
    # Imported lazily to avoid a circular freeze/runbook dependency.
    from scripts.compatibility.freeze_handoff import verify_candidate
    with no_data_access(ROOT) as access:
        gate=verify_candidate(candidate,expected_sha)
        publication=publication_gate(datetime.now(timezone.utc),datetime.fromisoformat(cfg(16)['publication_maturity_utc']))
        result=execution_contract(candidate_integrity=gate['integrity_passed'],methodology_consistent=gate['methodology_consistent'],
            technical_ready=gate['technical_ready_synthetic'],source_seed_status='ACCESS_APPROVAL_REQUIRED',
            publication_mature=publication['assumed_publication_mature'],user_authorized=False)
        return {'gates':result,'publication':publication,'candidate_verification':gate,'source_access':access,
            'actual_execution_command_implemented':False,'actual_mode':'ALWAYS_DENIED'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['preflight','actual'],required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--expected-sha',required=True)
    p.add_argument('--authorization-id');p.add_argument('--run-id');p.add_argument('--output',type=Path);a=p.parse_args()
    if a.mode=='actual':deny_actual_evaluation()  # before any candidate, source, forecast or ledger access
    if a.output is None or a.output.exists():raise ValueError('New preflight output required')
    if not a.output.resolve().is_relative_to(ROOT/'artifacts/day16'):raise ValueError('Day16 metadata output only')
    v=preflight(a.candidate.resolve(),a.expected_sha);save(a.output,v);print(json.dumps(v))


if __name__=='__main__':main()
