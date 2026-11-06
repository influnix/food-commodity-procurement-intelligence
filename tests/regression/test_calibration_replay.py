"""Explicit toy inputs and pinned SYNTHETIC archives; no network or actual source."""
from dataclasses import replace
from datetime import date,timedelta
import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0,str(ROOT/'scripts/compatibility'))
from scripts.compatibility.replay_support import cfg,read,load_saved_batches,no_data_access,preservation
from scripts.compatibility.calibration_replay import counterexample_regression,models,replay_stream
from scripts.compatibility.methodology_audit import toy_batch
from food_procurement_intelligence.data.sequential import SessionPermit,SequentialObservationStore,canonical_hash
from food_procurement_intelligence.evaluation.splits import load_split_plans,decision_at,LeakageError
from food_procurement_intelligence.forecasting.publisher import load_issued_forecast,NativeForecastPublisher
from food_procurement_intelligence.uncertainty.calibration import calibrate,OOFPool,finite_sample_adjustment
from food_procurement_intelligence.uncertainty.horizon_sequential import HorizonSequentialOOF
from food_procurement_intelligence.uncertainty.validity import validate_forecast,assert_native_raw

PLAN=load_split_plans(ROOT/'configs/evaluation/splits.toml')[0]
PERMIT=SessionPermit('DAY15_TOY_NO_FIT','DAY15_SYNTHETIC_ONLY')


@pytest.fixture(scope='module')
def counters():return counterexample_regression()


@pytest.mark.parametrize('i',range(16))
def test_archived_counterexamples_match_horizon_calibration_after_remediation(counters,i):
    c=counters['cases'][i]
    for h in c['horizons']:
        assert h['day5_count']==h['day12_count']
        assert h['day5_status']==h['day12_status']
        assert h['day5_adjustment']==h['day12_adjustment']
        assert h['day5_bounds']==h['day12_bounds']
    if c['joint']['paths_compared']:assert c['joint']['prices_equal']


def test_four_before_results_preserved_and_now_changed(counters):
    assert counters['changed_vs_day14_interval_or_fallback_rows']==4
    assert counters['joint_path_pairs_unchanged']==896


@pytest.mark.parametrize('change,state',[
    ({},'VALID_RAW'),({'q50':float('nan')},'INVALID_QUANTILE'),({'q50':float('inf')},'INVALID_QUANTILE'),
    ({'point_prediction':float('nan')},'INVALID_POINT'),({'point_prediction':float('inf')},'INVALID_POINT'),
    ({'lower_bound':float('nan')},'INVALID_INTERVAL'),({'upper_bound':float('inf')},'INVALID_INTERVAL'),
    ({'lower_bound':120.},'INVALID_INTERVAL'),({'q10':105.,'lower_bound':105.},'QUANTILE_CROSSING'),
    ({'q50':120.},'QUANTILE_CROSSING'),({'q10':120.,'lower_bound':120.},'QUANTILE_CROSSING'),
    ({'q10':0.,'lower_bound':0.},'NONPOSITIVE_BOUND_REVIEW'),({'q10':-5.,'lower_bound':-5.},'NONPOSITIVE_BOUND_REVIEW'),
    ({'point_prediction':0.},'INVALID_POINT'),({'point_prediction':-1.},'INVALID_POINT'),
    ({'point_prediction':'100'},'INVALID_POINT'),({'q50':'100'},'INVALID_QUANTILE'),
    ({'point_prediction':True},'INVALID_POINT'),({'q50':None},'INVALID_QUANTILE'),
    ({'lower_bound':89.},'INVALID_QUANTILE')])
def test_shared_stage_validity_and_no_invalid_laundering(change,state):
    p=replace(toy_batch(date(2021,6,1),PERMIT).raw[0],**change)
    v=validate_forecast(p);assert state in v.states
    corrected,_=calibrate(p,(),PLAN,cfg(5))
    if state in ('VALID_RAW','NONPOSITIVE_BOUND_REVIEW'):
        assert p.interval_usable and corrected.calibration_status=='insufficient_raw_fallback'
        assert corrected.lower_bound==p.lower_bound and corrected.upper_bound==p.upper_bound
        assert_native_raw(p)  # 0/negative finite statistical bounds are retained, not clipped
    else:
        assert not p.interval_usable and not corrected.interval_usable
        assert corrected.calibration_status=='raw_invalid_uncalibrated'
        assert corrected.lower_bound is None and corrected.upper_bound is None
        assert corrected.validity_status!='valid'
        if state not in ('QUANTILE_CROSSING',):
            with pytest.raises(ValueError):assert_native_raw(p)
    assert str(corrected.point_prediction)==str(p.point_prediction)


def test_point_and_quantile_median_are_not_substituted():
    p=replace(toy_batch(date(2021,6,1),PERMIT).raw[0],point_prediction=101.)
    assert p.q50==100. and p.point_prediction==101. and p.interval_usable
    out,_=calibrate(p,(),PLAN,cfg(5));assert out.point_prediction==101. and out.base_q50==100.


def test_invalid_interval_can_still_have_valid_joint_point(counters):
    c=next(c for c in counters['cases'] if c['case']=='crossing_excluded_from_scores_not_joint')
    assert c['joint']['day12_vector_count']==24 and c['joint']['prices_equal']
    assert c['horizons'][0]['day12_count']==0


@pytest.fixture(scope='module')
def seeds():
    with no_data_access(ROOT):
        batches=load_saved_batches()
    return tuple(b for (label,o),b in batches.items() if o<date(2024,9,1))


def pool(permit=PERMIT):return HorizonSequentialOOF(permit,cfg(5),cfg(6)['scenarios'],PLAN,models())


def seed_permit(seeds):
    return SessionPermit('DAY15_RESTORED_SYNTHETIC',json.loads(seeds[0].proof_json)['source_id'])


def test_synthetic_archive_restore_different_session_and_no_gap_backfill(seeds):
    p=pool(seed_permit(seeds));p.restore_seed_archive(seeds,canonical_hash([b.record() for b in seeds]))
    assert len(p.pending)==192 and len(p.calibration_pending)==576
    assert not any(date(2024,6,1)<=o<=date(2024,8,1) for _,o in p.pending)
    assert {phase for _,phase in p.pending.values()}=={'historical_train','validation'}


@pytest.mark.parametrize('fault',['hash','missing_batch','source','knowledge','model','session','history_proof','model_proof'])
def test_archive_tampering_rejected_atomically(seeds,fault):
    batches=list(seeds);b=batches[0];proof=json.loads(b.proof_json)
    if fault=='missing_batch':batches.pop()
    elif fault=='source':proof['source_id']='OTHER_SOURCE';batches[0]=replace(b,proof_json=json.dumps(proof))
    elif fault=='knowledge':batches[0]=replace(b,knowledge_type='actual_world_bank')
    elif fault=='model':batches[0]=replace(b,raw=tuple(replace(p,model_name='other_model') for p in b.raw))
    elif fault=='session':proof['source_session']='';batches[0]=replace(b,proof_json=json.dumps(proof))
    elif fault=='history_proof':proof['history_end']='2099-01';batches[0]=replace(b,proof_json=json.dumps(proof))
    elif fault=='model_proof':proof['model_spec_sha256']='';batches[0]=replace(b,proof_json=json.dumps(proof))
    digest='wrong' if fault=='hash' else canonical_hash([v.record() for v in batches])
    p=pool(seed_permit(seeds))
    with pytest.raises((ValueError,LeakageError)):p.restore_seed_archive(batches,digest)
    assert not p.pending and not p.released and not p.calibration_pending


@pytest.mark.parametrize('fault',['horizon','origin','fit_cutoff','publication','issuance'])
def test_immutable_batch_rejects_bad_original_proofs(seeds,fault):
    b=seeds[0];proof=json.loads(b.proof_json)
    with pytest.raises((ValueError,LeakageError)):
        if fault=='horizon':replace(b,raw=(b.raw[0],b.raw[2],b.raw[1]))
        elif fault=='origin':replace(b,origin=date(2024,6,1))
        elif fault=='fit_cutoff':replace(b.raw[0],fit_information_end=b.origin)
        elif fault=='publication':replace(b.raw[0],fit_max_label_available_at=decision_at(b.origin)+timedelta(seconds=1))
        else:proof['target_unobserved_at_issue']=False;replace(b,proof_json=json.dumps(proof))


def test_batch_reload_external_digest_and_mutation(seeds,tmp_path):
    b=seeds[0];p=tmp_path/'synthetic_issuance.json'
    p.write_text(json.dumps({'issued_sha256':b.digest,**b.record()}),encoding='utf-8')
    assert load_issued_forecast(p,b.digest).digest==b.digest
    row=json.loads(p.read_text());row['raw'][0]['point_prediction']+=1;p.write_text(json.dumps(row))
    with pytest.raises(ValueError):load_issued_forecast(p,b.digest)


def test_duplicate_forecast_and_wrong_model_rejected():
    p=pool();s=SequentialObservationStore(PERMIT);s.advance(date(2021,6,1));p.tick(s,s.clock)
    b=toy_batch(s.clock,PERMIT);p.issue(b,'validation')
    with pytest.raises(LeakageError):p.issue(b,'validation')
    wrong=replace(b,raw=tuple(replace(r,model_name='lightgbm_direct') for r in b.raw))
    with pytest.raises(LeakageError):p.calibrate(wrong)


def test_polluted_calibration_horizon_or_model_not_silently_accepted():
    p=pool();p.clock=date(2021,6,1)
    p.calibration_released['sarimax_110_10012',date(2020,1,1),1]={'model':'other','source_origin':date(2020,1,1),'horizon':1}
    with pytest.raises(LeakageError):p.calibration_residuals('sarimax_110_10012',p.clock,1)


def test_real_source_permit_and_opens_still_blocked():
    with pytest.raises(PermissionError):SessionPermit('x','x',real_data_authorized=True)
    with no_data_access(ROOT) as access:
        with pytest.raises(PermissionError):(ROOT/'data/raw/DAY15_NEVER_OPEN').read_bytes()
    assert access['actual_source_opens']==0 and len(access['blocked_attempts'])==1


def test_intentional_change_ledger_is_scoped_to_authorized_files():
    # Day15's frozen ledger is historical evidence; Day16 has its own scoped ledger.
    with no_data_access(ROOT):
        p=read(ROOT/'artifacts/day15/change_ledger.json')
        before=read(ROOT/'artifacts/day16/preservation_before.json')
    assert p['passed'] and not p['unauthorized_changes']
    assert {r['path'] for r in p['intentional_changes']}==set(cfg(15)['intentional_changes'])
    assert all(before['files'][r['path']]==r['after_sha256'] for r in p['intentional_changes'])


def test_no_fit_during_archived_regression(counters):
    with patch.object(NativeForecastPublisher,'publish',side_effect=AssertionError('No fit')):
        assert counterexample_regression()['all_equal_day5']


@pytest.fixture(scope='module')
def replay():
    with no_data_access(ROOT),patch.object(NativeForecastPublisher,'publish',side_effect=AssertionError('No fits')):
        return replay_stream()


def test_all_saved_joint_vectors_and_116_planning_sets_unchanged(replay):
    from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
    from scripts.compatibility.replay_support import D12
    assert _serializable(replay['pool_audit'])==read(D12/'pool_audit.json.gz')
    assert _serializable(replay['oof_released'])==read(D12/'oof_released.json.gz')
    assert len(replay['oof_released'])==228 and len(replay['pool_audit'])==116
    assert all(len(b.paths)==128 and sum(p.weight for p in b.paths)==1 for b in replay['scenarios'].values())


@pytest.mark.parametrize('label,counts',[('final_shape',(22,24,132)),('validation_shape',(36,38,216))])
def test_seven_policy_synthetic_e2e_exact_saved_metrics(replay,label,counts):
    from food_procurement_intelligence.evaluation.sequential_runner import EvaluationCalendar,run_policy_calendar
    from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
    from scripts.compatibility.replay_support import D12
    calendar=EvaluationCalendar(date(2024,9,1),date(2026,6,1),date(2026,9,1)) if label=='final_shape' else EvaluationCalendar(PLAN.validation_origin_start,PLAN.validation_origin_end,PLAN.validation_target_end)
    with no_data_access(ROOT):r=run_policy_calendar(replay,calendar,cfg(4),cfg(6),cfg(7),cfg(8))
    assert r['complete'] and len(r['results'])==7 and r['optimal_solves']==counts[2]
    assert _serializable(r['metrics'])==read(D12/label/'metrics.json')
    for row in r['results'].values():
        assert len(row['decision_audit'])==counts[0] and len(row['ledger'])==counts[1]
        assert all(v['new_order_quantity']==0 for v in row['ledger'][-3:])
        assert row['ledger'][-1]['outstanding_quantity']==0
        assert all(v['terminal_cost']==0 for v in row['ledger'][:-1])
    for model in ('sarimax','lightgbm'):
        assert [p['planning_scenarios'] for p in r['plans']['rn_'+model]]==[p['planning_scenarios'] for p in r['plans']['ra_'+model]]


def test_restored_archive_delayed_h3_releases_h1_h2_only(seeds):
    from food_procurement_intelligence.evaluation.sequential_runner import synthetic_observations,release_publications
    permit=seed_permit(seeds);s=SequentialObservationStore(permit);p=pool(permit)
    p.restore_seed_archive(seeds,canonical_hash([b.record() for b in seeds]))
    values=tuple(replace(v,actual_available_at=decision_at(date(2024,10,1))) if v.observation_month==date(2024,8,1) else v for v in synthetic_observations(cfg(12)))
    release_publications(s,values,date(2024,9,1));p.tick(s,s.clock)
    for model in models().values():
        assert (model,date(2024,5,1)) not in p.released
        assert (model,date(2024,5,1),1) in p.calibration_released
        assert (model,date(2024,5,1),2) in p.calibration_released
        assert (model,date(2024,5,1),3) not in p.calibration_released
    release_publications(s,values,date(2024,10,1));p.tick(s,s.clock)
    assert all((m,date(2024,5,1)) in p.released for m in models().values())


def test_new_candidate_requires_new_digest_and_pins(monkeypatch,tmp_path):
    import freeze
    from food_procurement_intelligence.evaluation.release_gate import REQUIRED_CHECKS,release_status
    monkeypatch.setattr(freeze,'ROOT',tmp_path)
    p=tmp_path/'artifacts/day15/candidate.json';p.parent.mkdir(parents=True)
    code=tmp_path/'toy_source.txt';code.write_text('toy');h=__import__('hashlib').sha256(code.read_bytes()).hexdigest()
    gate=release_status({k:'PASS' for k in REQUIRED_CHECKS})
    value={'kind':'DAY15_REMEDIATED_SYNTHETIC_CANDIDATE','contract_files':{'toy_source.txt':h},
        'code_files':{'toy_source.txt':h},'metadata_files':{'toy_source.txt':h},'actual_holdout_execution_allowed':False,
        'user_authorized':False,'holdout_locked':True,'release_gate':gate}
    p.write_text(json.dumps(value));digest=__import__('hashlib').sha256(p.read_bytes()).hexdigest()
    assert freeze.verify_candidate(p,digest)['status']=='READY'
    assert freeze.verify_candidate(p,'old_digest')['status']=='BLOCKED'
    code.write_text('changed')
    assert freeze.verify_candidate(p,digest)['status']=='BLOCKED'
    assert freeze.verify_candidate(tmp_path/'artifacts/day12/old.json','old_digest')['status']=='BLOCKED'
