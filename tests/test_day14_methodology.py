"""Audit counterexamples document existing behavior; they do NOT approve known gaps."""
from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/day14'))
from audit import (counterexamples,invalid_probes,toy_batch,no_data_access,config,plan,
    saved_synthetic_audit,verify_upstream,readiness,CANDIDATE,CANDIDATE_SHA,ROOT as AUDIT_ROOT)
from food_procurement_intelligence.data.sequential import SessionPermit,SequentialObservationStore
from food_procurement_intelligence.evaluation.splits import LeakageError,decision_at
from food_procurement_intelligence.evaluation.readiness import verify_candidate
from food_procurement_intelligence.uncertainty.sequential import SequentialOOF
from food_procurement_intelligence.uncertainty.calibration import finite_sample_adjustment


@pytest.fixture(scope='module')
def cases():return {r['case']:r for r in counterexamples()}


@pytest.mark.parametrize('name,old,new',[
    ('h1_only',[1],False),('h1_h2_only',[1,2],False),('all_horizons',[1,2,3],True),
    ('late_h3_plus_one_second',[1,2],False),('h3_at_exact_cutoff',[1,2,3],True),('late_h1_blocks_vector',[2,3],False)])
def test_actual_horizon_release_and_publication_boundaries(cases,name,old,new):
    assert cases[name]['last_origin_day5_released_horizons']==old
    assert cases[name]['last_origin_day12_released'] is new


@pytest.mark.parametrize('n,selected,rank',[(23,23,20),(24,24,20),(59,59,48),(60,60,49),(61,60,49)])
def test_recent60_min24_and_finite_rank(cases,n,selected,rank):
    c=cases[f'pool_{n}']
    for r in c['horizons']:
        assert r['day5_count']==r['day12_count']==selected
        assert r['day5_rank']==r['day12_rank']==rank
        assert r['day5_status']==r['day12_status']==('calibrated' if n>=24 else 'insufficient_raw_fallback')
    if n==61:assert c['horizons'][0]['day5_selected_origins'][0]=='2015-02'


def test_fallback_contract_actually_diverges(cases):
    for r in cases['fallback_divergence_23_plus_partial']['horizons'][:2]:
        assert (r['day5_count'],r['day12_count'])==(24,23)
        assert (r['day5_status'],r['day12_status'])==('calibrated','insufficient_raw_fallback')
        assert r['day5_bounds']!=r['day12_bounds']


def test_same_size_different_window_changes_interval(cases):
    r=cases['window_divergence_60_plus_partial']['horizons'][0]
    assert r['day5_count']==r['day12_count']==60
    assert (r['day5_adjustment'],r['day12_adjustment'])==(60.,59.)
    assert r['day5_selected_origins']!=r['day12_selected_origins']


def test_joint_full_vector_unchanged_by_calibration_release(cases):
    for r in cases.values():
        j=r['joint'];assert j['origins_equal'] and j['ratios_equal']
        if j['paths_compared']:assert j['prices_equal'] and j['sampled_origins_equal']
        else:assert j['insufficient_joint_rejected']


def test_unissued_origin_does_not_create_scores(cases):
    r=cases['unissued_origin_not_backfilled']
    assert all(h['day5_count']==h['day12_count']==0 for h in r['horizons'])


def test_models_remain_separate(cases):
    r=cases['mixed_models_separate_pools']
    assert len(r['models_present'])==2
    assert all(h['day5_count']==h['day12_count']==24 for h in r['horizons'])


def test_point_forecasts_unchanged_by_both_calibrators(cases):
    assert all(h['point_unchanged'] for c in cases.values() for h in c['horizons'])


def test_crossing_excludes_score_not_point_ratio_vector(cases):
    r=cases['crossing_excluded_from_scores_not_joint']
    assert r['horizons'][0]['day5_count']==r['horizons'][0]['day12_count']==0
    assert r['joint']['day6_vector_count']==r['joint']['day12_vector_count']==24
    assert r['joint']['prices_equal']


@pytest.mark.parametrize('kind',['crossing','inverted','nonfinite_bound'])
def test_invalid_raw_is_not_successful_fallback(kind):
    r=next(r for r in invalid_probes() if r['case']==kind)
    assert not r['raw_interval_usable']
    assert r['day5_status']==r['day12_status']=='raw_invalid_uncalibrated'
    assert not r['day5_output_usable'] and not r['day12_output_usable']


def test_documents_existing_nonfinite_quantile_gap_requires_cr02():
    # Preserve the Day14 counterexample; Day15 must fix the live behavior.
    saved=json.loads((ROOT/'artifacts/day14/evidence_a/quantile_crossing_fallback_audit.json').read_text(encoding='utf-8'))
    prior=next(r for r in saved['synthetic_invalid_probes'] if r['case']=='nonfinite_quantile')
    assert prior['raw_interval_usable'] and prior['output_validity']=='valid'
    r=next(r for r in invalid_probes() if r['case']=='nonfinite_quantile')
    assert not r['raw_interval_usable'] and r['base_nonfinite_or_missing']
    assert r['output_validity']!='valid' and r['finding']=='CR-02'
    assert r['day5_status']==r['day12_status']=='raw_invalid_uncalibrated'
    assert r['native_publisher_would_reject']


def test_documents_existing_nonfinite_point_calibration_gap():
    r=next(r for r in invalid_probes() if r['case']=='nonfinite_point')
    assert not r['raw_interval_usable'] and r['finding']=='CR-02'
    assert r['day5_status']==r['day12_status']=='raw_invalid_uncalibrated'
    assert 'nonfinite_point' in r['output_validity']


def test_negative_finite_bound_kept_and_flagged():
    r=next(r for r in invalid_probes() if r['case']=='negative_bound')
    assert r['raw_interval_usable'] and 'nonpositive' in r['raw_validity']
    assert r['native_publisher_would_reject']  # documented Day12 stronger ingress contract


@pytest.mark.parametrize('api',['path','builtins','os'])
def test_actual_source_open_blocked_before_read(api):
    import os
    with no_data_access(ROOT) as a:
        p=ROOT/'data/raw/DAY14_POISON_NEVER_OPEN'
        with pytest.raises(PermissionError):
            if api=='path':p.read_bytes()
            elif api=='builtins':open(p,'rb')
            else:os.open(p,os.O_RDONLY)
    assert len(a['blocked_attempts'])==1 and a['actual_source_opens']==0


def test_original_candidate_and_evidence_preserved():
    with no_data_access(ROOT):
        # Day16 explicitly appends README; archive outputs and its old prefix remain pinned.
        sys.path.insert(0,str(ROOT/'scripts/day16'))
        from support import archived_day13_release,sha
        r=archived_day13_release()
        assert sha(ROOT/CANDIDATE)==CANDIDATE_SHA
    assert r['reference_full_hashes']+r['declared_readme_prefix_reference']==61
    assert r['archived_release_bytes_unchanged'] and not r['current_readme_full_hash_is_old_pin']


def test_changed_freeze_cannot_reuse_approval(tmp_path):
    from hashlib import sha256
    p=tmp_path/'toy_candidate.json';p.write_text('{"toy":1}')
    old=sha256(p.read_bytes()).hexdigest();p.write_text('{"toy":2}')
    assert verify_candidate(p,old,tmp_path)['status']=='BLOCKED'
    assert verify_candidate(ROOT/CANDIDATE,'old-day11-digest',ROOT)['status']=='BLOCKED'


def test_no_session_or_model_proof_substitution():
    permit=SessionPermit('DAY14_TOY_NO_FIT','DAY14_MANUAL_TOY_NOT_WORLD_BANK')
    s=SequentialObservationStore(permit);s.advance(date(2021,6,1))
    pool=SequentialOOF(permit,config(5),config(6)['scenarios'],plan());pool.tick(s,s.clock)
    b=toy_batch(s.clock,SessionPermit('OTHER_SESSION',permit.source_id))
    with pytest.raises(LeakageError):pool.calibrate(b)
    with pytest.raises(LeakageError):pool.scenarios(b,'planning')


def test_same_input_deterministic_counterexamples(cases):
    assert cases=={r['case']:r for r in counterexamples()}


def test_readiness_not_automatically_promoted():
    r={v['state']:v['status'] for v in readiness()}
    assert r['MVP_COMPLETE']==r['TECHNICAL_READY']=='PASS'
    assert r['METHODOLOGY_CONSISTENT']=='ACTION_REQUIRED'
    assert r['SOURCE_PROVENANCE_VERIFIED']==r['PUBLICATION_MATURE']=='NOT_VERIFIED'
    assert r['USER_AUTHORIZED']==r['HOLDOUT_EXECUTION_ALLOWED']=='false'


def test_day14_harness_never_fits_or_runs_policy(monkeypatch):
    from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher
    def forbidden(*args,**kwargs):raise AssertionError('Day14 must not fit')
    monkeypatch.setattr(NativeForecastPublisher,'publish',forbidden)
    assert len(counterexamples())==16
