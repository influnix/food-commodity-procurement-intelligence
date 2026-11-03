"""Freeze Day16 handoff evidence; does not grant source access or evaluation capability."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from support import ROOT,cfg,read,save,sha,no_data_access,preservation,archived_day13_release
from food_procurement_intelligence.evaluation.final_contract import FINAL_CALENDAR,publication_gate,execution_contract
from food_procurement_intelligence.evaluation.release_gate import REQUIRED_CHECKS,release_status
from food_procurement_intelligence.evaluation.pre_holdout_audit import environment_audit


def verify_candidate(path:Path,expected_sha:str) -> dict:
    def fail(reason):return {'integrity_passed':False,'methodology_consistent':False,'technical_ready_synthetic':False,
        'status':'BLOCKED','reason':reason,'actual_holdout_execution_allowed':False}
    path=path.resolve()
    if not path.is_relative_to(ROOT/'artifacts/day16'):return fail('prior_candidate_not_valid_for_new_wiring')
    if not path.is_file() or sha(path)!=expected_sha:return fail('digest_changed_or_wrong_approval')
    v=read(path)
    if v.get('kind')!='DAY16_FINAL_HANDOFF_CANDIDATE':return fail('wrong_candidate_kind')
    for group in ('contract_files','code_files','evidence_files'):
        if not v.get(group):return fail('missing_'+group)
        for name,h in v[group].items():
            p=(ROOT/name).resolve()
            if not p.is_relative_to(ROOT) or p.is_relative_to(ROOT/'data'):return fail('forbidden_pin_path')
            if not p.is_file() or sha(p)!=h:return fail('pinned_file_changed:'+name)
    if v.get('actual_holdout_execution_allowed') is not False or v.get('user_authorized') is not False or not v.get('holdout_locked'):
        return fail('actual_execution_or_authorization_forbidden')
    gate=v['technical_release_gate'];derived=release_status(gate['checks'])
    if gate!=derived or derived['status']!='READY':return fail('technical_gate_not_reproduced')
    return {'integrity_passed':True,'methodology_consistent':True,'technical_ready_synthetic':True,
        'status':'VERIFIED_HANDOFF_RESEARCH_ACCESS_APPROVAL_REQUIRED','source_seed_status':'ACCESS_APPROVAL_REQUIRED',
        'actual_holdout_execution_allowed':False,'holdout_locked':True}


def freeze(a:Path,b:Path,seed_path:Path) -> dict:
    with no_data_access(ROOT) as access:
        old=ROOT/cfg(16)['prior_candidate'];expected=cfg(16)['prior_candidate_sha256'];assert sha(old)==expected
        baseline=read(ROOT/'artifacts/day16/day15_integrity_before.json');assert baseline['gate']['status']=='READY'
        tests=read(ROOT/'artifacts/day16/test_results.json');independent=read(ROOT/'artifacts/day16/independent_verification.json')
        assert tests['passed'] and tests['previous_tests']==515 and independent['passed'] and independent['deterministic_files_equal']>0
        assert independent['run_manifest_sha256']==sha(a/'run_manifest.json')
        for d in (a,b):
            m=read(d/'run_manifest.json');assert m['complete']
            for name,h in m['outputs'].items():assert sha(d/name)==h
            for name,h in m['code_at_start'].items():assert sha(ROOT/name)==h
        seed=read(seed_path);assert seed['saved_seed_audit']=='PASS_WITH_LIMITATIONS' and seed['source_seed_status']=='ACCESS_APPROVAL_REQUIRED'
        preserved=preservation();assert preserved['passed'];archived=archived_day13_release();assert archived['mvp_complete']
        env=environment_audit(ROOT);assert env['all_pins_match'] and env['python_matches_3_11_5']
        save(ROOT/'artifacts/day16/environment.json',env);save(ROOT/'artifacts/day16/change_ledger.json',preserved)
        prior=read(old)
        changed_pins=[n for group in ('contract_files','code_files','metadata_files') for n,h in prior[group].items() if sha(ROOT/n)!=h]
        now=datetime.now(timezone.utc);publication=publication_gate(now,datetime.fromisoformat(cfg(16)['publication_maturity_utc']))
        gates=execution_contract(candidate_integrity=True,methodology_consistent=True,technical_ready=True,
            source_seed_status='ACCESS_APPROVAL_REQUIRED',publication_mature=publication['assumed_publication_mature'],user_authorized=False)
        states={'PORTFOLIO_MVP':'COMPLETE','FINAL_HOLDOUT_RESEARCH_EVALUATION':'PENDING AUTHORIZATION / SOURCE GATE',
            'METHODOLOGY_CONSISTENT':'PASS_CR01_CR02_AND_FINAL_SYNTHETIC_WIRING','TECHNICAL_READY':'PASS_SYNTHETIC',
            'SOURCE_PROVENANCE_VERIFIED':'NOT_VERIFIED','SAVED_SEED_EVIDENCE':'VERIFIED_RECONSTRUCTED_ASOF',
            'ACTUAL_SEED_RUNTIME_RESTORE':'NOT_VERIFIED','PUBLICATION_MATURE_UNDER_ASSUMPTION':publication['assumed_publication_mature'],
            'USER_AUTHORIZED':False,'HOLDOUT_EXECUTION_ALLOWED':False}
        save(ROOT/'artifacts/day16/readiness_matrix.json',{'states':states,'gates':gates,'publication':publication})
        technical=release_status({k:'PASS' for k in REQUIRED_CHECKS})
        contracts=['AGENTS.md','README.md',*[p.relative_to(ROOT).as_posix() for p in (ROOT/'configs').glob('*') if p.is_file()],
            *[p.relative_to(ROOT).as_posix() for p in (ROOT/'docs').glob('DAY16*.md')],
            'docs/DAY11_PRE_HOLDOUT_PROTOCOL.md','docs/DAY11_LIMITATIONS.md','docs/DAY15_METHOD_REMEDIATION.md','docs/DAY15_VALIDITY_CONTRACT.md']
        code=[p.relative_to(ROOT).as_posix() for top in ('src','scripts','tests') for p in (ROOT/top).rglob('*.py') if '__pycache__' not in p.parts]
        evidence=[p.relative_to(ROOT).as_posix() for d in (a,b) for p in d.rglob('*') if p.is_file()]
        evidence += [seed_path.relative_to(ROOT).as_posix(),cfg(16)['prior_candidate'],
            'artifacts/day13/evidence_a/evidence_release_manifest.json',
            *['artifacts/day16/'+n for n in ('preservation_before.json','append_only_before.json','day15_integrity_before.json','access_scope.json',
                'test_results.json','independent_verification.json','environment.json','change_ledger.json','readiness_matrix.json')]]
        value={'schema_version':16,'kind':'DAY16_FINAL_HANDOFF_CANDIDATE','created_at_utc':now.isoformat(),
            'contract_files':{n:sha(ROOT/n) for n in sorted(set(contracts))},'code_files':{n:sha(ROOT/n) for n in sorted(set(code))},
            'evidence_files':{n:sha(ROOT/n) for n in sorted(set(evidence))},'technical_release_gate':technical,
            'states':states,'execution_gates':gates,'publication':publication,'source_evidence_levels':seed['source'],
            'seed_scope':{k:v for k,v in seed.items() if k not in ('records','batches')},
            'final_calendar':FINAL_CALENDAR.record(),'policies':cfg(11)['policies'],'environment':env,'test_result':tests,
            'synthetic_dress_rehearsal':read(a/'dress_summary.json'),'independent_verification':independent,
            'changes':preserved['intentional_changes'],'prior_candidate_sha256':expected,'prior_candidate_changed_live_pins':changed_pins,
            'prior_digest_valid_for_new_wiring':False,'day13_archive':archived,'actual_source_access':access,
            'user_authorized':False,'actual_holdout_execution_allowed':False,'holdout_locked':True,
            'actual_execution_command_implemented':False,
            'approval_binding':'Handoff and synthetic readiness only. Actual source access and evaluation need separate explicit scope, verified adapters, a fresh eligible digest, and authorization. This manifest grants none.'}
        p=ROOT/'artifacts/day16'/('candidate_'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        if p.exists():raise FileExistsError(p)
        save(p,value);h=sha(p)
        assert verify_candidate(p,h)['integrity_passed']
        assert verify_candidate(old,expected)['status']=='BLOCKED'
        pointer={'candidate':p.relative_to(ROOT).as_posix(),'sha256':h,'source_seed_status':'ACCESS_APPROVAL_REQUIRED',
            'portfolio_mvp':'COMPLETE','actual_holdout_execution_allowed':False,'holdout_locked':True}
        if (ROOT/'artifacts/day16/candidate_pointer.json').exists():raise FileExistsError('Do not overwrite prior handoff')
        save(ROOT/'artifacts/day16/candidate_pointer.json',pointer);return pointer


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('canonical',type=Path);p.add_argument('repeat',type=Path)
    p.add_argument('--seed-audit',type=Path,required=True);a=p.parse_args()
    print(json.dumps(freeze(a.canonical.resolve(),a.repeat.resolve(),a.seed_audit.resolve())))
