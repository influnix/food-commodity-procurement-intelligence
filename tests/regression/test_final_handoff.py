"""Scoped saved evidence + explicit synthetic final contract. No source price reads."""
from copy import deepcopy
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0,str(ROOT/'scripts/compatibility'))
from scripts.compatibility.handoff_support import cfg,read,sha,no_data_access,archived_portfolio_release,preservation
from scripts.compatibility.legacy_seed_audit import audit,validate_forecast_keys,saved_rows
from scripts.compatibility.final_rehearsal import prepare,future_mutation_prefix,SavedSyntheticPublisher
from food_procurement_intelligence.data.sequential import SessionPermit,SequentialObservationStore
from food_procurement_intelligence.evaluation.final_contract import (FINAL_CALENDAR,prepare_final_synthetic_stream,publication_gate,execution_contract)
from food_procurement_intelligence.evaluation.sequential_runner import synthetic_observations,release_publications,run_policy_calendar
from food_procurement_intelligence.evaluation.splits import load_split_plans,months_between,parse_month_label,add_months
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher


@pytest.fixture(scope='module')
def seed():return audit()


def test_saved_actual_seed_exact_calendar_hashes_and_no_backfill(seed):
    assert seed['forecast_records']==576 and seed['origin_model_batches']==192
    assert seed['historical_origins_per_model']==60 and seed['validation_origins_per_model']==36
    assert seed['existing_saved_residuals_verified']==558 and seed['existing_forecasts_with_newly_joined_saved_actual_evidence']==18
    assert not seed['unissued_2024_06_08_backfilled'] and seed['new_forecasts_or_fits']==0
    assert all(b['full_vector_mature_by_first_final_origin'] for b in seed['batches'])


def test_saved_seed_is_reconstructed_not_live_or_synthetic(seed):
    assert {r['knowledge_type'] for r in seed['records']}=={'reconstructed_asof_world_bank_snapshot'}
    assert all(not r['contemporaneous_live_issuance_verified'] for r in seed['records'])
    assert seed['runtime_restore'].startswith('BLOCKED_')
    with pytest.raises(PermissionError):SessionPermit('no','no',knowledge_type='reconstructed_asof_world_bank_snapshot')


def test_source_grade_requires_access_and_does_not_forge_vintage(seed):
    assert seed['source_seed_status']=='ACCESS_APPROVAL_REQUIRED'
    assert seed['source']['raw_current_bytes']=='NOT_VERIFIED'
    assert seed['source']['raw_hash_evidence_level']=='DOCUMENTED_PREVIOUS_HASH'
    assert seed['source']['saved_evidence_bytes']=='VERIFIED_CURRENT_BYTES'
    assert seed['source']['historical_vintage']==seed['source']['actual_historical_release_timestamp']=='NOT_VERIFIED'
    assert not seed['source']['source_provenance_verified']
    assert not seed['additional_access_request']['whole_original_file_loading_or_rehash_authorized']


def toy_keys():
    d4,d5=cfg(4),cfg(5)
    origins=months_between(parse_month_label(d5['historical_origin_start']),parse_month_label(d5['historical_origin_end']))+months_between(date(2021,6,1),date(2024,5,1))
    return [{'model_name':d4[label]['model_name'],'forecast_origin':f'{o:%Y-%m}','horizon':str(h),
        'target_month':f'{add_months(o,h):%Y-%m}','phase':'historical_train' if o<=date(2021,3,1) else 'validation'}
        for label in ('sarimax','lightgbm') for o in origins for h in (1,2,3)]


@pytest.mark.parametrize('fault',['duplicate','missing','unissued','model','horizon','target','phase','actual_column'])
def test_seed_scope_checked_before_numeric_decoding(fault):
    rows=toy_keys()
    if fault=='duplicate':rows[-1]=rows[0]
    elif fault=='missing':rows.pop()
    elif fault=='unissued':rows[0]['forecast_origin']='2024-06'
    elif fault=='model':rows[0]['model_name']='synthetic_or_other_model'
    elif fault=='horizon':rows[0]['horizon']='4'
    elif fault=='target':rows[0]['target_month']='2024-10'
    elif fault=='phase':rows[0]['phase']='holdout'
    else:rows[0]['actual_price']='NEVER_DECODE_THIS'
    with pytest.raises(ValueError):validate_forecast_keys(rows,cfg(4),cfg(5))


def test_unpinned_or_source_path_not_accepted_as_saved_evidence(tmp_path):
    p=tmp_path/'toy.csv';p.write_text('toy\n')
    with pytest.raises(ValueError):saved_rows(p,'wrong')
    with pytest.raises(ValueError):saved_rows(ROOT/'data/raw/NEVER_READ','wrong')


@pytest.fixture(scope='module')
def stream():
    with no_data_access(ROOT),patch.object(NativeForecastPublisher,'publish',side_effect=AssertionError('No new fit')):
        return prepare()


def test_final_runner_explicit_horizon_adapter_and_maturity(stream):
    assert stream['final_wiring']['calibration_adapter']=='HorizonSequentialOOF'
    assert stream['final_wiring']['calibration_release']=='horizon' and stream['final_wiring']['joint_release']=='full_vector'
    rows=[r for r in stream['calibration_audit'] if r['model']=='sarimax_110_10012' and r['origin']==date(2021,6,1)]
    assert [r['count'] for r in rows]==[60,60,59]
    first=next(r for r in stream['pool_audit'] if r['model']=='sarimax_110_10012' and r['origin']==date(2021,6,1))
    assert first['pool_n']==59


@pytest.mark.parametrize('fault',['actual_source','calendar','calibration','scenario'])
def test_final_wrapper_rejects_source_or_contract_change_before_publisher(fault):
    c,d4,d5,d6=cfg(12),cfg(4),cfg(5),cfg(6);values=list(synthetic_observations(c))
    if fault=='actual_source':values[0]=replace(values[0],knowledge_type='actual_world_bank')
    elif fault=='calendar':c['first_origin']='2024-10'
    elif fault=='calibration':d5['minimum_calibration_samples']=25
    else:d6['scenarios']['planning_seed']+=1
    with pytest.raises((ValueError,PermissionError)):
        prepare_final_synthetic_stream(c,d4,d5,d6,load_split_plans(ROOT/'configs/evaluation/splits.toml')[0],values,publisher_factory=lambda *a:pytest.fail('publisher must not be created'))


def test_final_synthetic_seven_policy_e2e_and_state_independence(stream):
    with no_data_access(ROOT):r=run_policy_calendar(stream,FINAL_CALENDAR,cfg(4),cfg(6),cfg(7),cfg(8))
    assert r['complete'] and len(r['results'])==7 and r['optimal_solves']==132
    assert sum(len(v['decision_audit']) for v in r['results'].values())==154
    assert sum(len(v['ledger']) for v in r['results'].values())==168
    assert _serializable(r['metrics'])==read(ROOT/'artifacts/day15/evidence_a/final_shape/metrics.json')
    for v in r['results'].values():
        assert v['decision_audit'][0]['context']['on_hand_tonnes']==200
        assert not v['decision_audit'][0]['context']['outstanding_orders']
        assert all(row['new_order_quantity']==0 for row in v['ledger'][-3:])
        assert all(row['terminal_cost']==0 for row in v['ledger'][:-1])
        assert v['ledger'][-1]['outstanding_quantity']==0
    for model in ('sarimax','lightgbm'):
        assert [p['planning_scenarios'] for p in r['plans']['rn_'+model]]==[p['planning_scenarios'] for p in r['plans']['ra_'+model]]


def test_future_input_mutation_leaves_past_orders_unchanged(stream):
    with no_data_access(ROOT):result=future_mutation_prefix(stream)
    assert result['passed'] and len(result['policies'])==7
    assert not result['new_stress_world_or_performance_evaluation']


def test_replay_blocks_unissued_forecast_and_duplicate_clock():
    publisher=SavedSyntheticPublisher(cfg(4),())
    s=SequentialObservationStore(SessionPermit('DAY12_NATIVE_STREAM_V1','DAY12_AR_INCREMENTS_SEED20261030'))
    values=synthetic_observations(cfg(12));release_publications(s,values,date(2016,4,1))
    publisher.publish(s,s.clock)
    with pytest.raises(ValueError):publisher.publish(s,s.clock)
    release_publications(s,values,date(2024,6,1))
    with pytest.raises(LookupError):publisher.publish(s,s.clock)


def test_raw_validity_and_point_stay_separate_from_quantile():
    from scripts.compatibility.methodology_audit import toy_batch
    from food_procurement_intelligence.uncertainty.calibration import calibrate
    p=toy_batch(date(2021,6,1),SessionPermit('DAY16_TOY','DAY16_TOY')).raw[0]
    bad=replace(p,q50=float('nan'))
    out,_=calibrate(bad,(),load_split_plans(ROOT/'configs/evaluation/splits.toml')[0],cfg(5))
    assert not out.interval_usable and out.calibration_status=='raw_invalid_uncalibrated' and out.point_prediction==100.


@pytest.mark.parametrize('delta,mature',[(-1,False),(0,True),(1,True)])
def test_publication_gate_boundaries_do_not_prove_actual_release(delta,mature):
    threshold=datetime(2026,10,31,23,59,59,tzinfo=timezone.utc)
    r=publication_gate(threshold+timedelta(seconds=delta),threshold)
    assert r['assumed_publication_mature'] is mature and not r['actual_historical_release_timestamp_verified']


def test_naive_publication_clock_rejected():
    with pytest.raises(ValueError):publication_gate(datetime(2026,11,1),datetime(2026,11,1,tzinfo=timezone.utc))


@pytest.mark.parametrize('authorization',[False,True])
def test_user_authorization_never_creates_missing_execution_capability(authorization):
    r=execution_contract(candidate_integrity=True,methodology_consistent=True,technical_ready=True,
        source_seed_status='ACCESS_APPROVAL_REQUIRED',publication_mature=True,user_authorized=authorization)
    assert r['F_user_authorized'] is authorization and not r['G_actual_execution_permission'] and r['holdout_locked']


def test_actual_runbook_mode_denied_before_any_reader(monkeypatch):
    import runbook
    monkeypatch.setattr(sys,'argv',['runbook','--mode','actual','--candidate','NEVER_OPEN','--expected-sha','no','--authorization-id','not_approval'])
    with patch.object(runbook,'preflight',side_effect=AssertionError('No reader')):
        with pytest.raises(PermissionError):runbook.main()


@pytest.mark.parametrize('path',['data/raw/NEVER_OPEN_MIXED_XLSX','data/processed/NEVER_OPEN_801_CSV','data/NEVER_OPEN_BRIDGE_HOLDOUT'])
def test_source_bridge_holdout_access_blocked_before_open(path):
    with no_data_access(ROOT) as access:
        with pytest.raises(PermissionError):(ROOT/path).read_bytes()
    assert access['actual_source_opens']==0 and len(access['blocked_attempts'])==1


def test_existing_mvp_archive_and_candidate_bytes_preserved():
    with no_data_access(ROOT):
        assert archived_portfolio_release()['mvp_complete']
        assert sha(ROOT/cfg(16)['prior_candidate'])==cfg(16)['prior_candidate_sha256']
        assert preservation()['passed']


def test_candidate_kind_digest_and_changed_pin_block_old_approval(tmp_path,monkeypatch):
    import handoff
    from food_procurement_intelligence.evaluation.release_gate import release_status,REQUIRED_CHECKS
    monkeypatch.setattr(handoff,'ROOT',tmp_path)
    p=tmp_path/'artifacts/day16/candidate.json';p.parent.mkdir(parents=True)
    f=tmp_path/'toy.txt';f.write_text('toy')
    value={'kind':'DAY16_FINAL_HANDOFF_CANDIDATE','contract_files':{'toy.txt':sha(f)},'code_files':{'toy.txt':sha(f)},'evidence_files':{'toy.txt':sha(f)},
        'actual_holdout_execution_allowed':False,'user_authorized':False,'holdout_locked':True,'technical_release_gate':release_status({k:'PASS' for k in REQUIRED_CHECKS})}
    from scripts.compatibility.handoff_support import save
    save(p,value);digest=sha(p)
    assert handoff.verify_candidate(p,digest)['integrity_passed']
    assert handoff.verify_candidate(p,'old_digest')['status']=='BLOCKED'
    f.write_text('changed');assert handoff.verify_candidate(p,digest)['status']=='BLOCKED'
    assert handoff.verify_candidate(tmp_path/'artifacts/day15/old.json','old')['status']=='BLOCKED'


def test_saved_seed_audit_repeat_determinism(seed):
    assert audit()==seed
