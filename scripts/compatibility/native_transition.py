"""Legacy fixture seed -> fresh native final origins -> unchanged seven-policy synthetic world."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path

from scripts.compatibility.legacy_support import ROOT,D12,cfg,read,save,zipped,sha,no_data_access,preservation,validator_fixture,manifest_hash,access_specification
from scripts.compatibility.legacy_evidence import actual_legacy_evidence,synthetic_legacy_archive,models,model_hashes
from food_procurement_intelligence.data.sequential import SessionPermit,SequentialObservationStore,canonical_hash
from food_procurement_intelligence.data.restricted_source import validate_export_bytes,require_real_source_verification,SourceAccessApprovalRequired
from food_procurement_intelligence.evaluation.splits import ForecastSample,months_between,add_months,load_split_plans
from food_procurement_intelligence.evaluation.sequential_runner import synthetic_observations,release_publications,run_policy_calendar
from food_procurement_intelligence.evaluation.final_contract import FINAL_CALENDAR
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.evaluation.model_backtesting import save_csv
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher,without_timing
from food_procurement_intelligence.uncertainty.provenance_sequential import ProvenanceSequentialOOF

D16=ROOT/'artifacts/day16/evidence_a'


def semantic(value):
    """Exclude pool lineage digest and its dependent Planning-record digest only."""
    if isinstance(value,dict):return {k:semantic(v) for k,v in value.items() if k not in ('pool_sha256','planning_sha256')}
    if isinstance(value,(tuple,list)):return [semantic(v) for v in value]
    return value


def prepare_transition(directory:Path|None=None):
    observations=synthetic_observations(cfg(12));legacy,archive_hash=synthetic_legacy_archive()
    old_hashes=[b.digest for b in legacy]
    permit=SessionPermit(cfg(17)['synthetic_session_id'],observations[0].source_id)
    store=SequentialObservationStore(permit);plan=load_split_plans(ROOT/'configs/evaluation/splits.toml')[0]
    pool=ProvenanceSequentialOOF(permit,cfg(5),cfg(6)['scenarios'],plan,models(),
        legacy_model_specs=model_hashes(),legacy_snapshot=observations[0].vintage_id)
    pool.restore_legacy_archive(legacy,archive_hash)
    candidates=tuple(ForecastSample(o,(1,2,3),tuple(add_months(o,h) for h in (1,2,3)))
        for o in months_between(add_months(observations[0].observation_month,13),FINAL_CALENDAR.last_origin))
    publisher=NativeForecastPublisher(cfg(4),candidates,directory/'native_issuances' if directory else None)
    pool.bind_native_issuer(publisher)
    baseline={}
    for p in sorted((D12/'issuances').glob('202*.json')):
        v=read(p)
        if v['origin']>='2024-09':baseline[v['label'],v['origin']]=v
    issued={};scenarios={};pools=[];corrected=[];cal_audits=[];release_audit=[];maximum_delta=0.
    for origin in FINAL_CALENDAR.origins:
        release_publications(store,observations,origin);pool.tick(store,origin)
        assert all(o<origin for _,o in pool.released)
        release_audit.append({'origin':origin,'calibration_scores_by_level':dict(Counter(pool.lineage[(m,o)]['evidence_level'] for m,o,h in pool.calibration_released)),
            'joint_vectors_by_level':dict(Counter(pool.lineage[(m,o)]['evidence_level'] for m,o in pool.released)),
            'current_origin_unreleased':True})
        for b in publisher.publish(store,origin):
            prior=baseline[b.label,f'{origin:%Y-%m}']['raw']
            for p,r in zip(b.raw,prior):
                for name in ('point_prediction','q10','q50','q90','lower_bound','upper_bound'):
                    delta=abs(getattr(p,name)-r[name]);maximum_delta=max(maximum_delta,delta)
                    if delta>cfg(17)['price_tolerance']:raise ValueError('Native same-input forecast changed beyond frozen tolerance')
            out,audit=pool.calibrate(b);corrected.extend(p.record() for p in out);cal_audits.extend(audit)
            bundles={}
            for purpose in ('planning','evaluation'):
                bundles[purpose],vectors=pool.scenarios(b,purpose)
            try:bundles['evaluation'].for_policy(origin)
            except ValueError:rejected=True
            else:raise ValueError('Evaluation scenario reached policy')
            key=b.label,origin;issued[key]=b;scenarios[key]=bundles['planning']
            pools.append({'origin':origin,'label':b.label,'model':b.raw[0].model_name,'phase':'sequential_synthetic',
                'pool_n':len(vectors),'vectors':vectors,'pool_sha256':bundles['planning'].pool_sha256,
                'planning_seed':str(bundles['planning'].seed),'evaluation_seed':str(bundles['evaluation'].seed),
                'evaluation_rejected':rejected,'planning_records':bundles['planning'].records()})
            pool.issue(b,'sequential_synthetic')
            assert (b.raw[0].model_name,origin) not in pool.released
    assert old_hashes==[b.digest for b in legacy],'Legacy values/provenance mutated'
    stream={'observations':observations,'store':store,'issued':issued,'scenarios':scenarios,'pool_audit':pools,
        'calibrated':corrected,'calibration_audit':cal_audits,'oof_released':list(pool.released.values()),'release_log':store.release_log,
        'lineage':[{'model':m,'origin':o,**v} for (m,o),v in pool.lineage.items()],
        'maturity_audit':release_audit,'legacy_archive_hash':archive_hash,'legacy_hashes_unchanged':True,
        'maximum_native_forecast_delta_vs_day12':maximum_delta,'native_events':without_timing(publisher.events),
        'native_timing':publisher.events,'pool':pool,'legacy':legacy}
    return stream


def run(output:Path):
    output=output.resolve()
    if not output.is_relative_to(ROOT/'artifacts/day17'):raise ValueError('New Day17 output folder required')
    output.mkdir(parents=True,exist_ok=False)
    code={p.relative_to(ROOT).as_posix():sha(p) for top in ('src','configs','scripts/compatibility') for p in sorted((ROOT/top).rglob('*')) if p.is_file() and p.suffix in ('.py','.toml','.json')}
    with no_data_access(ROOT) as access:
        actual,proof=actual_legacy_evidence();zipped(output/'saved_legacy_archive.json.gz',[b.record() for b in actual]);save(output/'saved_legacy_verification.json',proof)
        contract,payload,manifest=validator_fixture()
        report=validate_export_bytes(payload,manifest,contract.permitted_path,contract,expected_manifest_sha256=manifest_hash(manifest))
        save(output/'restricted_validator_synthetic.json',report)
        try:require_real_source_verification(contract)
        except SourceAccessApprovalRequired:pass
        else:raise AssertionError('Real source capability must stay disabled')
        save(output/'access_approval_request.json',access_specification())
        s=prepare_transition(output)
        baseline_pools=[v for v in read(D16/'pool_audit.json.gz') if v['origin']>='2024-09']
        assert len(baseline_pools)==44==len(s['pool_audit'])
        for new,old in zip(_serializable(s['pool_audit']),baseline_pools):
            assert new['model']==old['model'] and new['origin']==old['origin']
            assert new['planning_seed']==old['planning_seed'] and new['evaluation_seed']==old['evaluation_seed']
            assert semantic(new['planning_records'])==semantic(old['planning_records'])
            assert [v['source_origin'] for v in new['vectors']]==[v['source_origin'] for v in old['vectors']]
            assert [v['ratios'] for v in new['vectors']]==[v['ratios'] for v in old['vectors']]
        expected_cal=[p for p in read(D16/'calibrated.json.gz') if p['forecast_origin']>='2024-09']
        assert s['calibrated']==expected_cal,'Calibration numerics/status changed'
        for name in ('pool_audit','calibrated','calibration_audit','oof_released','lineage','maturity_audit','release_log'):
            zipped(output/(name+'.json.gz'),s[name])
        zipped(output/'synthetic_legacy_archive.json.gz',[b.record() for b in s['legacy']])
        save(output/'synthetic_observations.json',[asdict(v) for v in s['observations']])
        save(output/'native_events.json',s['native_events'])
        # Runtime-only durations are intentionally outside deterministic outputs.
        save(output/'native_timing.json',s['native_timing'])
        r=run_policy_calendar(s,FINAL_CALENDAR,cfg(4),cfg(6),cfg(7),cfg(8))
        if not r['complete']:raise RuntimeError('Incomplete synthetic transition E2E; no fallback/full comparison')
        target=output/'final_shape';target.mkdir();equal=0
        save(output/'final_shape_operations.json',{'settings':r['settings'],'suppliers':r['suppliers'],
            'knowledge_type':'synthetic_day12_not_world_bank','demand':100.,'realized_extra_delay':0,'initial_pipeline':[]})
        for name,v in r['results'].items():
            for kind in ('ledger','orders','receipts'):
                path=target/(name+'_'+kind+'.csv');save_csv(path,_serializable(v[kind]))
                if path.read_bytes()!=(D16/'final_shape'/path.name).read_bytes():raise ValueError('Policy flow changed despite same inputs')
                equal+=1
            save(target/(name+'_decision_audit.json'),v['decision_audit']);save(target/(name+'_runoff.json'),v['runoff_no_action'])
            zipped(target/(name+'_plans.json.gz'),r['plans'][name])
            assert semantic(read(target/(name+'_plans.json.gz')))==semantic(read(D16/'final_shape'/(name+'_plans.json.gz')))
        for name in ('metrics','monthly','paired','input_audit','calendar'):
            save(target/(name+'.json'),r[name]);assert semantic(read(target/(name+'.json')))==semantic(read(D16/'final_shape'/(name+'.json')))
        summary={'complete':True,'legacy_batches':192,'legacy_horizon_records':576,'new_native_batches':len(s['issued']),
            'new_native_sarimax_fits':sum(e['model']=='sarimax' for e in s['native_events']),
            'new_native_lightgbm_fits':sum(e['model']=='lightgbm' for e in s['native_events']),
            'decision_origins':22,'ledger_months':24,'active_months':21,'runoff_months':3,'policies':7,
            'decision_records':sum(len(v['decision_audit']) for v in r['results'].values()),'ledger_rows':sum(len(v['ledger']) for v in r['results'].values()),
            'optimal_lp_plans':r['optimal_solves'],'byte_equal_day16_flow_files':equal,'native_maximum_price_delta':s['maximum_native_forecast_delta_vs_day12'],
            'legacy_hashes_unchanged':True,'same_joint_paths':44*128,'actual_world_bank_fit_or_policy_evaluation':False,
            'lineage_pool_hash_changes_expected':True,'new_experiment_world':False,'hidden_fallback':0,'actual_holdout_execution_allowed':False}
        assert (summary['new_native_batches'],summary['decision_records'],summary['ledger_rows'],summary['optimal_lp_plans'])==(44,154,168,132)
        save(output/'integration_summary.json',summary)
        save(output/'methodology_impact.json',{'numeric_calibration_joint_policy_outputs':'UNCHANGED','only_pool_lineage_hashes':'CHANGED_BY_EXPLICIT_LEGACY_NATIVE_PROVENANCE',
            'legacy_evidence':'RECONSTRUCTED_ASOF','native_evidence':'NATIVE_ISSUED_THIS_SYNTHETIC_EXECUTION','promotion_or_native_proof_fabrication':False})
        p=preservation();assert p['passed'];save(output/'preservation.json',p);save(output/'source_access_audit.json',access)
        assert all(sha(ROOT/n)==h for n,h in code.items()),'Code changed during native integration'
        save(output/'run_manifest.json',{'kind':'DAY17_SYNTHETIC_LEGACY_NATIVE_TRANSITION','complete':True,'code_at_start':code,
            'outputs':{p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='native_timing.json'},
            'nondeterministic_outputs':['native_timing.json'],'actual_holdout_execution_allowed':False,'real_source_export_verified':False})
    return {'output':output.relative_to(ROOT).as_posix(),'summary':summary,'source_access':access}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(run(a.output)))
    except Exception as e:
        if a.output.is_dir():save(a.output/'failure.json',{'complete':False,'full_comparison_allowed':False,'error_type':type(e).__name__,'error':str(e)})
        raise
