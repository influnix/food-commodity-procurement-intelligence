"""New digest-bound synthetic Candidate. No approval/capability/unlock issuer."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
from datetime import datetime,timezone
from pathlib import Path
import argparse
import json

from scripts.compatibility.replay_support import ROOT,D12,cfg,read,save,sha,no_data_access,preservation
from food_procurement_intelligence.evaluation.release_gate import REQUIRED_CHECKS,release_status
from food_procurement_intelligence.evaluation.pre_holdout_audit import environment_audit,baseline_evidence


def verify_candidate(path:Path,expected_digest:str) -> dict:
    """Day15 kind/digest and all current pins required; old manifests cannot approve it."""
    def blocked(reason):return release_status({},[reason])
    if not path.resolve().is_relative_to(ROOT/'artifacts/day15'):return blocked('old_candidate_not_valid_for_day15')
    if not path.is_file() or sha(path)!=expected_digest:return blocked('candidate_digest_changed_or_stale_approval')
    v=read(path)
    if v.get('kind')!='DAY15_REMEDIATED_SYNTHETIC_CANDIDATE':return blocked('wrong_candidate_kind')
    for group in ('contract_files','code_files','metadata_files'):
        if not v.get(group):return blocked('missing_'+group)
        for name,h in v[group].items():
            p=(ROOT/name).resolve()
            if not p.is_relative_to(ROOT) or p.is_relative_to(ROOT/'data'):return blocked('forbidden_pin_path')
            if not p.is_file() or sha(p)!=h:return blocked('pinned_file_changed:'+name)
    if v['actual_holdout_execution_allowed'] or v['user_authorized'] or not v['holdout_locked']:
        return blocked('execution_or_authorization_not_allowed')
    derived=release_status(v['release_gate']['checks'])
    if derived!=v['release_gate']:return blocked('inconsistent_release_gate')
    return derived


def freeze(a:Path,b:Path) -> dict:
    with no_data_access(ROOT) as access:
        settings=cfg(15);prior=ROOT/settings['baseline_candidate']
        assert sha(prior)==settings['baseline_candidate_sha256']
        release=ROOT/'artifacts/day13/evidence_a/evidence_release_manifest.json'
        assert sha(release)==settings['day13_release_sha256']
        tests=read(ROOT/'artifacts/day15/test_results.json');verification=read(ROOT/'artifacts/day15/independent_verification.json')
        assert tests['passed'] and tests['previous_tests']==451 and verification['passed']
        assert verification['deterministic_files_equal']>0 and verification['run_manifest_sha256']==sha(a/'run_manifest.json')
        for d in (a,b):
            m=read(d/'run_manifest.json');assert m['complete']
            for name,h in m['outputs'].items():assert sha(d/name)==h
            for name,h in m['code_at_start'].items():assert sha(ROOT/name)==h
            assert read(d/'joint_invariance.json')['passed'] and read(d/'synthetic_e2e_regression.json')['passed']
            assert read(d/'seed_archive_verification.json')['synthetic_interface']=='PASS'
            assert read(d/'source_access_audit.json')=={'actual_source_opens':0,'blocked_attempts':[]}
        preserved=preservation();assert preserved['passed']
        environment=environment_audit(ROOT);assert environment['all_pins_match'] and environment['python_matches_3_11_5']
        baseline=baseline_evidence(ROOT);assert baseline['flow_files_rechecked_without_source_prices']==21
        save(ROOT/'artifacts/day15/baseline_environment.json',{'environment':environment,'day9_baseline':baseline})
        save(ROOT/'artifacts/day15/change_ledger.json',preserved)
        now=datetime.now(timezone.utc);threshold=datetime.fromisoformat(settings['publication_maturity_utc'])
        states={'MVP_COMPLETE':'PASS','TECHNICAL_READY':'PASS_SYNTHETIC','METHODOLOGY_CONSISTENT':'PASS_CR01_CR02',
            'CR03_SYNTHETIC_INTERFACE':'PASS','SOURCE_PROVENANCE_VERIFIED':'NOT_VERIFIED',
            'PUBLICATION_MATURE':now>=threshold,'USER_AUTHORIZED':False,'HOLDOUT_EXECUTION_ALLOWED':False}
        readiness={'states':states,'assessed_at_utc':now.isoformat(),'publication_rule_threshold_utc':threshold.isoformat(),
            'publication_clock_basis':'actual UTC clock; fixed project next-month-end assumption, never synthetic clock',
            'actual_release_timestamp_evidence':'NOT_VERIFIED','actual_seed_provenance':'NOT_VERIFIED',
            'real_new_origin_fit':'NOT_VERIFIED','real_data_capability_enabled':False,'holdout_locked':True}
        save(ROOT/'artifacts/day15/readiness_matrix.json',readiness)
        checks={name:'PASS' for name in REQUIRED_CHECKS};gate=release_status(checks)
        contract_names=['docs/DATA_AND_ASOF_CONTRACT.md','README.md','docs/LIMITATIONS_AND_FUTURE_WORK.md',*['configs/'+p.name for p in (ROOT/'configs').glob('*') if p.is_file()],
            *[p.relative_to(ROOT).as_posix() for p in (ROOT/'docs').glob('DAY15*.md')],
            'docs/UNCERTAINTY_AND_SCENARIOS.md','docs/UNCERTAINTY_AND_SCENARIOS.md','docs/PRODUCT_OVERVIEW.md',
            'docs/SYSTEM_ARCHITECTURE.md','docs/UNCERTAINTY_AND_SCENARIOS.md']
        code_names=[p.relative_to(ROOT).as_posix() for top in ('src','tests','scripts') for p in (ROOT/top).rglob('*.py') if '__pycache__' not in p.parts]
        evidence_names=[p.relative_to(ROOT).as_posix() for d in (a,b) for p in d.rglob('*') if p.is_file()]
        evidence_names += ['artifacts/day15/'+n for n in ('test_results.json','independent_verification.json','preservation_before.json',
            'upstream_before.json','baseline_environment.json','change_ledger.json','readiness_matrix.json')]
        evidence_names += [settings['baseline_candidate'],'artifacts/day13/evidence_a/evidence_release_manifest.json',
            'artifacts/day14/evidence_a/audit_manifest.json','artifacts/day14/evidence_a/synthetic_maturity_counterexamples.json']
        value={'schema_version':15,'kind':'DAY15_REMEDIATED_SYNTHETIC_CANDIDATE','created_at_utc':now.isoformat(),
            'contract_files':{n:sha(ROOT/n) for n in sorted(set(contract_names))},
            'code_files':{n:sha(ROOT/n) for n in sorted(set(code_names))},
            'metadata_files':{n:sha(ROOT/n) for n in sorted(set(evidence_names))},
            'source_metadata':read(prior)['source_metadata'],'source_metadata_basis':'previous recorded raw metadata only; no raw byte recheck',
            'changes':preserved['intentional_changes'],'CR01':'Day5 horizon maturity for calibration; Day6 full-vector joint retained',
            'CR02':'shared numeric/finite/ordering/endpoints/base provenance validation; nonpositive statistical bounds retain+flag; positive Joint points/prices',
            'CR03':'synthetic interface PASS; actual archive and vintage/release provenance NOT_VERIFIED',
            'test_status':tests,'independent_verification':verification,'release_gate':gate,'readiness':readiness,
            'actual_source_access':access,'actual_holdout_execution_allowed':False,'holdout_locked':True,'user_authorized':False,
            'previous_candidate_sha256':sha(prior),'day13_release_sha256':sha(release),
            'approval_binding':'Candidate digest identifies synthetic remediation evidence only; no user approval exists. Any code/contract/pin change needs a new verification/freeze and separately authorized actual evaluation.'}
        path=ROOT/'artifacts/day15'/('candidate_'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        if path.exists():raise FileExistsError(path)
        save(path,value);h=sha(path)
        assert verify_candidate(path,h)['status']=='READY'
        assert verify_candidate(prior,sha(prior))['status']=='BLOCKED'
        pointer={'candidate':path.relative_to(ROOT).as_posix(),'sha256':h,'actual_holdout_execution_allowed':False,'holdout_locked':True}
        if (ROOT/'artifacts/day15/candidate_pointer.json').exists():raise FileExistsError('New freeze needs new pointer name')
        save(ROOT/'artifacts/day15/candidate_pointer.json',pointer)
        return pointer


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('canonical',type=Path);p.add_argument('repeat',type=Path);a=p.parse_args()
    print(json.dumps(freeze(a.canonical.resolve(),a.repeat.resolve())))
