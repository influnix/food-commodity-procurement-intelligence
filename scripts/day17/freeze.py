"""Freeze typed Source/Legacy/Native contracts; real evaluation remains disabled."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path

from helpers import ROOT,cfg,read,save,sha,no_data_access,preservation,access_specification,archived_day13_release
from food_procurement_intelligence.evaluation.final_contract import publication_gate,FINAL_CALENDAR
from food_procurement_intelligence.evaluation.release_gate import release_status,REQUIRED_CHECKS
from food_procurement_intelligence.evaluation.pre_holdout_audit import environment_audit


def verify_candidate(path:Path,expected_sha:str) -> dict:
    def blocked(reason):return {'status':'BLOCKED','reason':reason,'actual_holdout_execution_allowed':False}
    p=path.resolve()
    if not p.is_relative_to(ROOT/'artifacts/day17'):return blocked('prior_digest_does_not_cover_day17_adapter')
    if not p.is_file() or sha(p)!=expected_sha:return blocked('candidate_digest_changed')
    v=read(p)
    if v.get('kind')!='DAY17_RESTRICTED_SOURCE_LEGACY_NATIVE_CANDIDATE':return blocked('wrong_candidate_kind')
    for group in ('contract_files','code_files','evidence_files'):
        if not v.get(group):return blocked('missing_'+group)
        for name,h in v[group].items():
            f=(ROOT/name).resolve()
            if not f.is_relative_to(ROOT) or f.is_relative_to(ROOT/'data'):return blocked('forbidden_pin_path')
            if not f.is_file() or sha(f)!=h:return blocked('changed_pin:'+name)
    if v['actual_holdout_execution_allowed'] or v['user_authorized'] or not v['holdout_locked']:return blocked('execution_not_authorized')
    gate=release_status(v['technical_release_gate']['checks'])
    if gate!=v['technical_release_gate'] or gate['status']!='READY':return blocked('technical_evidence_not_ready')
    return {'status':'VERIFIED_SYNTHETIC_CANDIDATE_REAL_SOURCE_NOT_VERIFIED','integrity_passed':True,
        'real_source_export_verified':False,'real_seed_runtime_verified':'NOT_VERIFIED','actual_holdout_execution_allowed':False}


def freeze(a:Path,b:Path):
    with no_data_access(ROOT) as access:
        prior=ROOT/cfg(17)['prior_candidate'];prior_sha=cfg(17)['prior_candidate_sha256'];assert sha(prior)==prior_sha
        # Existing pins remain valid: Day17 adds files instead of mutating old contracts.
        pv=read(prior)
        for group in ('contract_files','code_files','evidence_files'):
            for name,h in pv[group].items():assert sha(ROOT/name)==h
        tests=read(ROOT/'artifacts/day17/test_results.json');independent=read(ROOT/'artifacts/day17/independent_verification.json')
        assert tests['passed'] and tests['previous_tests']==549 and independent['passed'] and independent['deterministic_files_equal']>0
        assert independent['run_manifest_sha256']==sha(a/'run_manifest.json')
        for d in (a,b):
            m=read(d/'run_manifest.json');assert m['complete']
            for n,h in m['outputs'].items():assert sha(d/n)==h
            for n,h in m['code_at_start'].items():assert sha(ROOT/n)==h
            summary=read(d/'integration_summary.json');assert summary['complete'] and summary['new_native_batches']==44
            assert read(d/'saved_legacy_verification.json')['contract']['status']=='PASS_RECONSTRUCTED_CONTRACT'
            assert read(d/'source_access_audit.json')=={'actual_source_opens':0,'blocked_attempts':[]}
        preserved=preservation();assert preserved['passed'];mvp=archived_day13_release();assert mvp['mvp_complete']
        environment=environment_audit(ROOT);assert environment['all_pins_match'] and environment['python_matches_3_11_5']
        save(ROOT/'artifacts/day17/environment.json',environment);save(ROOT/'artifacts/day17/preservation.json',preserved)
        save(ROOT/'artifacts/day17/access_approval_request.json',access_specification())
        now=datetime.now(timezone.utc);publication=publication_gate(now,datetime.fromisoformat(cfg(17)['publication_maturity_utc']))
        states={'MVP_COMPLETE':'PASS','METHODOLOGY_CONSISTENT':'PASS','TECHNICAL_READY_SYNTHETIC':'PASS',
            'LEGACY_SEED_ADAPTER_READY':'PASS_SYNTHETIC_AND_SAVED_EVIDENCE_CONTRACT','REAL_SOURCE_EXPORT_VERIFIED':'REAL_SOURCE_NOT_VERIFIED',
            'REAL_SEED_RUNTIME_VERIFIED':'NOT_VERIFIED','PUBLICATION_MATURE':publication['assumed_publication_mature'],
            'USER_AUTHORIZED':False,'HOLDOUT_EXECUTION_ALLOWED':False}
        save(ROOT/'artifacts/day17/readiness_matrix.json',{'states':states,'publication':publication,
            'source_access_status':'ACCESS_APPROVAL_REQUIRED','actual_evaluation_cli_enabled':False})
        contracts=['AGENTS.md','README.md',*[p.relative_to(ROOT).as_posix() for p in (ROOT/'configs').glob('*') if p.is_file()],
            *[p.relative_to(ROOT).as_posix() for p in (ROOT/'docs').glob('DAY17*.md')],
            'docs/DAY15_VALIDITY_CONTRACT.md','docs/DAY15_METHOD_REMEDIATION.md','docs/DAY16_FINAL_RELEASE_PROTOCOL.md']
        code=[p.relative_to(ROOT).as_posix() for top in ('src','tests','scripts') for p in (ROOT/top).rglob('*.py') if '__pycache__' not in p.parts]
        evidence=[p.relative_to(ROOT).as_posix() for d in (a,b) for p in d.rglob('*') if p.is_file() and p.name!='native_timing.json']
        evidence+=[cfg(17)['prior_candidate'],*['artifacts/day17/'+n for n in ('test_results.json','independent_verification.json','preservation_before.json',
            'day16_integrity_before.json','environment.json','preservation.json','access_approval_request.json','readiness_matrix.json')]]
        value={'schema_version':17,'kind':'DAY17_RESTRICTED_SOURCE_LEGACY_NATIVE_CANDIDATE','created_at_utc':now.isoformat(),
            'contract_files':{n:sha(ROOT/n) for n in sorted(set(contracts))},'code_files':{n:sha(ROOT/n) for n in sorted(set(code))},
            'evidence_files':{n:sha(ROOT/n) for n in sorted(set(evidence))},'states':states,'publication':publication,
            'technical_release_gate':release_status({k:'PASS' for k in REQUIRED_CHECKS}),
            'legacy_contract':'RECONSTRUCTED_ASOF, no invented Native session/history/live proof',
            'native_contract':'NATIVE_ISSUED only from this synthetic execution publisher and successful native fits',
            'numeric_methodology':'unchanged Day15 horizon calibration / Day6 full vector joint / frozen model policies operations',
            'real_source_export_verified':False,'real_seed_runtime_verified':'NOT_VERIFIED','source_scope':access_specification(),
            'calendar':FINAL_CALENDAR.record(),'policies':cfg(11)['policies'],'test_results':tests,'independent_verification':independent,
            'environment':environment,'preservation':preserved,'existing_files_modified':[],
            'added_code_sha256':{n:h for n,h in {p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}.items()
                if n not in read(ROOT/'artifacts/day17/preservation_before.json')['files']},
            'prior_candidate_sha256':prior_sha,'prior_pins_preserved':True,'prior_digest_authorizes_added_day17_files':False,
            'actual_source_access':access,'user_authorized':False,'actual_holdout_execution_allowed':False,'holdout_locked':True,
            'historical_vintage':'NOT_VERIFIED','actual_historical_release_timestamp':'NOT_VERIFIED','contemporaneous_live_forecast_issuance':'NOT_VERIFIED',
            'approval_binding':'Candidate identifies synthetic integration and saved evidence only. No actual source or Holdout authorization/capability is granted.'}
        path=ROOT/'artifacts/day17'/('candidate_'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json');save(path,value);h=sha(path)
        assert verify_candidate(path,h)['integrity_passed'] and verify_candidate(prior,prior_sha)['status']=='BLOCKED'
        pointer={'candidate':path.relative_to(ROOT).as_posix(),'sha256':h,'actual_holdout_execution_allowed':False,'source_status':'ACCESS_APPROVAL_REQUIRED'}
        if (ROOT/'artifacts/day17/candidate_pointer.json').exists():raise FileExistsError('Do not overwrite candidate pointer')
        save(ROOT/'artifacts/day17/candidate_pointer.json',pointer);return pointer


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('canonical',type=Path);p.add_argument('repeat',type=Path);a=p.parse_args()
    print(json.dumps(freeze(a.canonical.resolve(),a.repeat.resolve())))
