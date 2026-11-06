"""Pure export fixtures, pinned saved evidence, and same-world synthetic native transition."""
from copy import deepcopy
from dataclasses import replace
from datetime import date,timedelta
import csv
import io
import hashlib
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0,str(ROOT/'scripts/compatibility'))
from scripts.compatibility.legacy_support import cfg,read,sha,no_data_access,validator_fixture,manifest_hash,source_contract,preservation
from scripts.compatibility.legacy_evidence import actual_legacy_evidence,synthetic_legacy_archive,models,model_hashes
from scripts.compatibility.native_transition import prepare_transition,semantic
from food_procurement_intelligence.data.restricted_source import validate_export_bytes,require_real_source_verification
from food_procurement_intelligence.data.sequential import canonical_hash,SessionPermit,SequentialObservationStore
from food_procurement_intelligence.forecasting.legacy import LegacyReconstructedForecast,NativeIssuedForecast,legacy_from_records,validate_legacy_archive,planning_points
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher
from food_procurement_intelligence.evaluation.splits import load_split_plans,LeakageError,decision_at
from food_procurement_intelligence.evaluation.sequential_runner import synthetic_observations,release_publications,run_policy_calendar
from food_procurement_intelligence.evaluation.final_contract import FINAL_CALENDAR,execution_contract
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.uncertainty.provenance_sequential import ProvenanceSequentialOOF
from food_procurement_intelligence.uncertainty.calibration import finite_sample_adjustment

PLAN=load_split_plans(ROOT/'configs/evaluation/splits.toml')[0]


def validate(c,p,m,path=None):return validate_export_bytes(p,m,path or c.permitted_path,c,expected_manifest_sha256=manifest_hash(m))


def test_exact_776_month_export_fixture_is_not_real_source_verification():
    c,p,m=validator_fixture();v=validate(c,p,m)
    assert v['structural_validation']=='PASS' and v['scope_months']==776
    assert v['real_source_verification']=='REAL_SOURCE_NOT_VERIFIED' and not v['actual_access_granted']
    assert v['historical_vintage']=='NOT_VERIFIED' and v['publication_evidence']=='ASSUMED_PUBLICATION_TIME'


@pytest.mark.parametrize('fault',['source','snapshot','unit','series','columns','start','end','rows','generator','basis','manifest_link','bridge','hash'])
def test_export_manifest_scope_and_provenance_changes_rejected(fault):
    c,p,m=validator_fixture()
    if fault=='source':m['source_identity']='OTHER'
    elif fault=='snapshot':m['snapshot_identity']='OTHER'
    elif fault=='unit':m['unit']='EUR/t'
    elif fault=='series':m['source_series']='Wheat, US SRW'
    elif fault=='columns':m['columns'].append('future_price')
    elif fault=='start':m['start']='1960-02'
    elif fault=='end':m['end']='2024-09'
    elif fault=='rows':m['rows']=801
    elif fault=='generator':m['generation_method']='load_mixed801_then_filter'
    elif fault=='basis':m['generation_basis']=''
    elif fault=='manifest_link':m['source_reference']['raw_sha256']='0'*64
    elif fault=='bridge':m['bridge_holdout_included']=True
    else:m['export_sha256']='wrong'
    with pytest.raises(ValueError):validate(c,p,m)


@pytest.mark.parametrize('fault',['duplicate','missing','unsorted','bridge','holdout','zero','negative','nan','inf','text','unit','series','vintage','availability','naive','extra_column'])
def test_export_rows_reject_expansion_invalid_values_and_future_months(fault):
    c,p,m=validator_fixture();rows=list(csv.DictReader(io.StringIO(p.decode())));columns=list(rows[0])
    if fault=='duplicate':rows[-1]=rows[0].copy()
    elif fault=='missing':rows.pop()
    elif fault=='unsorted':rows[0],rows[1]=rows[1],rows[0]
    elif fault in ('bridge','holdout'):
        rows[-1]['observation_month']='2024-09' if fault=='bridge' else '2024-10';rows[-1]['price']='DO_NOT_DECODE_FUTURE'
    elif fault in ('zero','negative','nan','inf','text'):rows[0]['price']={'zero':'0','negative':'-1','nan':'NaN','inf':'Infinity','text':'True'}[fault]
    elif fault=='unit':rows[0]['unit']='index'
    elif fault=='series':rows[0]['source_series']='OTHER'
    elif fault=='vintage':rows[0]['vintage_id']='first_historical_release_claim'
    elif fault=='availability':rows[0]['available_at']='1960-01-31T23:59:59+00:00'
    elif fault=='naive':rows[0]['available_at']='1960-02-29T23:59:59'
    else:
        columns.append('future_price')
        for r in rows:r['future_price']='DO_NOT_DECODE'
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=columns);w.writeheader();w.writerows(rows);p=s.getvalue().encode()
    m['export_sha256']=hashlib.sha256(p).hexdigest()
    with pytest.raises(ValueError):validate(c,p,m)


def test_path_and_external_manifest_pin_checked_before_source_read():
    c,p,m=validator_fixture()
    with pytest.raises(ValueError):validate(c,p,m,ROOT/'data/raw/mixed801.csv')
    with pytest.raises(ValueError):validate_export_bytes(p,m,c.permitted_path,c,expected_manifest_sha256='old')
    with patch('builtins.open',side_effect=AssertionError('Never open actual source')):
        with pytest.raises(PermissionError):require_real_source_verification(c)


@pytest.fixture(scope='module')
def actual():return actual_legacy_evidence()


def test_actual_saved_192_batches_576_forecasts_keep_low_evidence(actual):
    batches,proof=actual
    assert len(batches)==192 and sum(len(b.raw) for b in batches)==576
    assert proof['saved_residuals_verified']==558 and proof['already_issued_forecasts_joined_to_saved_actuals']==18
    assert proof['real_seed_runtime_verified']=='NOT_VERIFIED'
    assert all(type(b) is LegacyReconstructedForecast and not hasattr(b,'proof_json') for b in batches)
    assert all(b.knowledge_type=='RECONSTRUCTED_ASOF' and b.historical_issuance_evidence_level=='NOT_VERIFIED' for b in batches)


def test_legacy_serialization_retains_ids_values_and_no_native_envelope(actual):
    batches,proof=actual;records=[b.record() for b in batches]
    loaded=legacy_from_records(records,proof['archive_sha256_derived_today'])
    assert [b.digest for b in loaded]==[b.digest for b in batches]
    assert all(planning_points(a)==planning_points(b) for a,b in zip(batches,loaded))
    assert all(r['native_session_proof'] is None and r['original_input_byte_proof'] is None for r in records)


@pytest.mark.parametrize('fault',['archive_hash','promotion','native_session','input_bytes','record_id','model','origin','horizon'])
def test_legacy_archive_tamper_or_evidence_promotion_rejected(actual,fault):
    batches,proof=actual;r=deepcopy([b.record() for b in batches])
    if fault=='promotion':r[0]['knowledge_type']='NATIVE_ISSUED'
    elif fault=='native_session':r[0]['native_session_proof']='MADE_UP'
    elif fault=='input_bytes':r[0]['original_input_byte_proof']='MADE_UP'
    elif fault=='record_id':r[0]['original_record_ids'][0]='changed'
    elif fault=='model':r[0]['raw'][0]['model_name']='other'
    elif fault=='origin':r[0]['origin']='2024-06'
    elif fault=='horizon':r[0]['raw'][0]['horizon']=3
    digest=proof['archive_sha256_derived_today'] if fault=='archive_hash' else canonical_hash(r)
    if fault=='archive_hash':r[0]['snapshot_identity']='changed'
    with pytest.raises((ValueError,TypeError)):legacy_from_records(r,digest)


@pytest.fixture(scope='module')
def legacy():return synthetic_legacy_archive()


def pool():
    permit=SessionPermit(cfg(17)['synthetic_session_id'],'DAY12_AR_INCREMENTS_SEED20261030')
    return ProvenanceSequentialOOF(permit,cfg(5),cfg(6)['scenarios'],PLAN,models(),legacy_model_specs=model_hashes(),legacy_snapshot='SYNTHETIC_DAY12_V1')


@pytest.mark.parametrize('fault',['missing','duplicate','unissued','wrong_source','wrong_spec','wrong_snapshot','native_type'])
def test_restore_exact_legacy_calendar_source_and_atomic_rejection(legacy,fault):
    batches,h=legacy;b=list(batches)
    if fault=='missing':b.pop()
    elif fault=='duplicate':b[-1]=b[0]
    elif fault=='unissued':
        old=b[0];o=date(2024,6,1)
        raw=tuple(replace(p,forecast_origin=o,information_cutoff=date(2024,5,1),target_month=date(2024,6+p.horizon,1)) for p in old.raw)
        b[0]=replace(old,origin=o,raw=raw,original_record_ids=tuple(p.record()['record_id'] for p in raw))
    elif fault=='wrong_source':b[0]=replace(b[0],source_identity='OTHER')
    elif fault=='wrong_spec':b[0]=replace(b[0],model_spec_sha256='0'*64)
    elif fault=='wrong_snapshot':b[0]=replace(b[0],snapshot_identity='OTHER')
    else:b[0]=object()
    p=pool()
    with pytest.raises((ValueError,TypeError)):
        digest=canonical_hash([v.record() for v in b]) if fault!='native_type' else 'not_native'
        p.restore_legacy_archive(b,digest)
    assert not p.pending and not p.calibration_pending


def test_real_saved_legacy_cannot_be_mixed_into_synthetic_store(actual):
    b,proof=actual
    with pytest.raises(LeakageError):pool().restore_legacy_archive(b,proof['archive_sha256_derived_today'])


def test_legacy_horizon_release_and_joint_wait_for_h3(legacy):
    b,h=legacy;p=pool();p.restore_legacy_archive(b,h)
    s=SequentialObservationStore(p.permit)
    values=tuple(replace(v,actual_available_at=decision_at(date(2024,10,1))) if v.observation_month==date(2024,8,1) else v for v in synthetic_observations(cfg(12)))
    release_publications(s,values,date(2024,9,1));p.tick(s,s.clock)
    for m in models().values():
        assert (m,date(2024,5,1)) not in p.released
        assert (m,date(2024,5,1),1) in p.calibration_released and (m,date(2024,5,1),2) in p.calibration_released
        assert (m,date(2024,5,1),3) not in p.calibration_released
    release_publications(s,values,date(2024,10,1));p.tick(s,s.clock)
    assert all((m,date(2024,5,1)) in p.released for m in models().values())


@pytest.mark.parametrize('n,rank',[(23,20),(24,20),(59,48),(60,49),(61,50)])
def test_original_finite_sample_rank_and_minimum(n,rank):
    value,k=finite_sample_adjustment(list(map(float,range(n))),.8,24)
    assert k==rank and (value is None)==(n<24)


@pytest.fixture(scope='module')
def transition():
    with no_data_access(ROOT):return prepare_transition()


def test_seed_to_fresh_native_transition_keeps_two_types(transition):
    s=transition
    assert len(s['legacy'])==192 and len(s['issued'])==44 and len(s['native_events'])==286
    assert all(type(b) is NativeIssuedForecast for b in s['issued'].values())
    assert s['legacy_hashes_unchanged'] and s['maximum_native_forecast_delta_vs_day12']<=1e-8
    assert {r['evidence_level'] for r in s['lineage']}=={'RECONSTRUCTED_ASOF','NATIVE_ISSUED'}
    assert all(r['native_session'] is None for r in s['lineage'] if r['evidence_level']=='RECONSTRUCTED_ASOF')


def test_first_origin_restores_legacy_new_native_waits_for_maturity(transition):
    rows=transition['maturity_audit'];assert len(rows)==22
    assert rows[0]['joint_vectors_by_level']=={'RECONSTRUCTED_ASOF':192}
    assert rows[0]['calibration_scores_by_level']=={'RECONSTRUCTED_ASOF':566}
    assert rows[1]['joint_vectors_by_level'].get('NATIVE_ISSUED',0)==0
    assert rows[2]['calibration_scores_by_level']['NATIVE_ISSUED']==2
    assert rows[4]['joint_vectors_by_level']['NATIVE_ISSUED']==2


def test_unissued_native_and_legacy_new_origin_are_rejected(legacy):
    from scripts.compatibility.methodology_audit import toy_batch
    p=pool();b,h=legacy;p.restore_legacy_archive(b,h)
    with pytest.raises(TypeError):p.issue(b[0],'sequential_synthetic')
    fake=toy_batch(date(2024,9,1),p.permit)
    with pytest.raises(LeakageError):p.calibrate(fake)


def test_common_planning_view_does_not_promote_legacy(transition):
    for b in transition['legacy'][:3]:
        assert len(planning_points(b))==3 and b.knowledge_type=='RECONSTRUCTED_ASOF'
    for b in list(transition['issued'].values())[:2]:assert planning_points(b)==b.points()


def test_final_same_world_seven_policy_outputs_preserved(transition):
    with no_data_access(ROOT):r=run_policy_calendar(transition,FINAL_CALENDAR,cfg(4),cfg(6),cfg(7),cfg(8))
    assert r['complete'] and r['optimal_solves']==132 and len(r['results'])==7
    assert _serializable(r['metrics'])==read(ROOT/'artifacts/day16/evidence_a/final_shape/metrics.json')
    assert sum(len(v['decision_audit']) for v in r['results'].values())==154
    assert sum(len(v['ledger']) for v in r['results'].values())==168
    for m in ('sarimax','lightgbm'):
        assert [v['planning_scenarios'] for v in r['plans']['rn_'+m]]==[v['planning_scenarios'] for v in r['plans']['ra_'+m]]


def test_future_unpublished_changes_do_not_change_first_orders(transition):
    from scripts.compatibility.final_rehearsal import future_mutation_prefix
    with no_data_access(ROOT):assert future_mutation_prefix(transition)['passed']


def test_source_open_permission_and_execution_stay_disabled():
    with no_data_access(ROOT) as access:
        with pytest.raises(PermissionError):(ROOT/cfg(17)['proposed_export']).read_bytes()
    assert access['actual_source_opens']==0 and len(access['blocked_attempts'])==1
    with pytest.raises(PermissionError):SessionPermit('x','x',real_data_authorized=True)
    r=execution_contract(candidate_integrity=True,methodology_consistent=True,technical_ready=True,source_seed_status='NOT_VERIFIED',publication_mature=True,user_authorized=True)
    assert not r['G_actual_execution_permission']


def test_existing_files_unchanged_and_saved_contract_repeat(actual):
    assert preservation()['passed']
    again,proof=actual_legacy_evidence()
    assert [b.digest for b in again]==[b.digest for b in actual[0]] and proof==actual[1]


def test_candidate_added_code_needs_new_digest_and_prior_approval_rejected(tmp_path,monkeypatch):
    # Import Day17 by file identity: existing regressions also have a module named freeze.
    import importlib.util
    spec=importlib.util.spec_from_file_location('day17_candidate',ROOT/'scripts/compatibility/freeze_legacy_candidate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);monkeypatch.setattr(module,'ROOT',tmp_path)
    from food_procurement_intelligence.evaluation.release_gate import release_status,REQUIRED_CHECKS
    p=tmp_path/'artifacts/day17/candidate.json';p.parent.mkdir(parents=True);f=tmp_path/'toy.txt';f.write_text('toy')
    from scripts.compatibility.legacy_support import save
    value={'kind':'DAY17_RESTRICTED_SOURCE_LEGACY_NATIVE_CANDIDATE','contract_files':{'toy.txt':sha(f)},
        'code_files':{'toy.txt':sha(f)},'evidence_files':{'toy.txt':sha(f)},'actual_holdout_execution_allowed':False,
        'user_authorized':False,'holdout_locked':True,'technical_release_gate':release_status({k:'PASS' for k in REQUIRED_CHECKS})}
    save(p,value);h=sha(p);assert module.verify_candidate(p,h)['integrity_passed']
    assert module.verify_candidate(p,'old')['status']=='BLOCKED'
    assert module.verify_candidate(tmp_path/'artifacts/day16/old.json','old')['status']=='BLOCKED'
    f.write_text('changed');assert module.verify_candidate(p,h)['status']=='BLOCKED'
