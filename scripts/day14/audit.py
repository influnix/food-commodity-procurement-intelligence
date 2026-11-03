"""Day14 read-only methodology audit. Toy records only; never fit or run policies."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timedelta
import gzip
import hashlib
import json
from pathlib import Path
from random import Random
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_day13_evidence import no_data_access
from food_procurement_intelligence.data.sequential import Observation, SessionPermit, SequentialObservationStore
from food_procurement_intelligence.evaluation.splits import add_months, decision_at, load_split_plans
from food_procurement_intelligence.forecasting.publisher import IssuedForecast, load_issued_forecast
from food_procurement_intelligence.uncertainty.calibration import OOFPool, calibrate
from food_procurement_intelligence.uncertainty.contracts import UncertaintyPrediction
from food_procurement_intelligence.uncertainty.joint_scenarios import SavedOOFForecasts, derived_seed, generate_joint_scenarios
from food_procurement_intelligence.uncertainty.sequential import SequentialOOF

D12 = 'artifacts/day12/run_20261030T152324128300Z_6ef590c2'
CANDIDATE = 'artifacts/day12/candidate_20261030T153217902819Z.json'
CANDIDATE_SHA = 'ae093042b0cfbe3b8af5a75d01e235f12faa5adb82fd0438527286a0006b6a4f'
RELEASE = 'artifacts/day13/evidence_a/evidence_release_manifest.json'
RELEASE_SHA = '7f22d01c68e09d21242fd5d726fbec566b911162b78a2ecc05ebff12de1236c0'
MODELS = {'sarimax': ('sarimax_110_10012', 'sarimax_native'), 'lightgbm': ('lightgbm_direct', 'lightgbm_quantile')}


def read(path: Path):
    content = path.read_bytes()
    return json.loads(gzip.decompress(content) if path.suffix == '.gz' else content)


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False, default=str) + '\n', encoding='utf-8')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config(day: int) -> dict:
    return tomllib.loads((ROOT / f'configs/day{day}.toml').read_text(encoding='utf-8'))


def plan():
    return load_split_plans(ROOT / 'configs/splits.toml')[0]


def toy_batch(origin: date, permit: SessionPermit, label: str = 'sarimax', invalid: str | None = None) -> IssuedForecast:
    """Manually specified synthetic counterexample, NOT native fitting evidence.

    IssuedForecast requires its native backend tag. It is only an API fixture here;
    events and proof explicitly say no fit and cannot establish native provenance.
    """
    model, method = MODELS[label]
    cutoff = add_months(origin, -1)
    rows = []
    for h in (1, 2, 3):
        p = UncertaintyPrediction(model, method, origin, cutoff, add_months(origin, h), h,
            100., 90., 100., 110., 90., 110., cutoff, decision_at(origin))
        if h == 1:
            if invalid == 'crossing': p = replace(p, q10=105., q50=100., lower_bound=105.)
            elif invalid == 'inverted': p = replace(p, lower_bound=120., upper_bound=110.)
            elif invalid == 'nonfinite_bound': p = replace(p, lower_bound=float('inf'))
            elif invalid == 'nonfinite_quantile': p = replace(p, q50=float('nan'))
            elif invalid == 'nonfinite_point': p = replace(p, point_prediction=float('nan'))
            elif invalid == 'negative_bound': p = replace(p, q10=-1., lower_bound=-1.)
        rows.append(p)
    proof = {'forecast_origin': f'{origin:%Y-%m}', 'information_cutoff': f'{cutoff:%Y-%m}',
        'training_origin_end': f'{add_months(origin,-4):%Y-%m}', 'last_complete_training_target': f'{cutoff:%Y-%m}',
        'max_training_available_at': decision_at(origin).isoformat(), 'target_unobserved_at_issue': True,
        'source_id': permit.source_id, 'source_session': permit.session_id, 'toy_manual_no_fit': True}
    return IssuedForecast(origin, label, tuple(rows), json.dumps(proof, sort_keys=True),
        json.dumps([{'status': 'toy_manual_no_fit'}]))


def compare(origins: tuple[date, ...], evaluation: date, *, delayed_h: int | None = None,
            delay_seconds: int = 1, invalid: str | None = None, mixed: bool = False,
            joint: bool = False) -> dict:
    """Exercise unmodified Day5, Day6, Day12 APIs with identical toy issuance/actuals."""
    permit = SessionPermit('DAY14_TOY_NO_FIT', 'DAY14_MANUAL_TOY_NOT_WORLD_BANK')
    store = SequentialObservationStore(permit)
    d5, sc, p = config(5), config(6)['scenarios'], plan()
    old, new = OOFPool(p), SequentialOOF(permit, d5, sc, p)
    labels = ('sarimax', 'lightgbm') if mixed else ('sarimax',)
    batches = [toy_batch(o, permit, label, invalid) for o in origins for label in labels]
    all_targets = sorted({r.target_month for b in batches for r in b.raw})
    observations = []
    for m in all_targets:
        index = (m.year - 2015) * 12 + m.month - 1
        available = decision_at(add_months(m, 1))
        if delayed_h and m == add_months(origins[-1], delayed_h):
            available = decision_at(evaluation) + timedelta(seconds=delay_seconds)
        observations.append(Observation(m, 120. + index, available, 'explicit_toy_timestamp',
            'DAY14_TOY', permit.source_id))
    pending = sorted(observations, key=lambda a: (a.actual_available_at, a.observation_month))
    for clock in sorted(set(origins) | {evaluation}):
        store.advance(clock)
        for a in list(pending):
            if a.observation_month <= add_months(clock,-1) and a.actual_available_at <= decision_at(clock):
                store.publish(a); pending.remove(a)
        old.release(store, clock); new.tick(store, clock)
        for b in batches:
            if b.origin == clock:
                old.add(b.raw, 'historical_train'); new.issue(b, 'historical_train')
    current = toy_batch(evaluation, permit)
    corrected, new_audit = new.calibrate(current)
    horizons = []
    for i, raw in enumerate(current.raw):
        before, audit = calibrate(raw, tuple(old.released.values()), p, d5)
        now = corrected[i]
        horizons.append({'horizon': i+1, 'day5_count': audit['selected_n'], 'day12_count': new_audit[i]['count'],
            'day5_status': before.calibration_status, 'day12_status': now.calibration_status,
            'day5_adjustment': before.calibration_adjustment, 'day12_adjustment': now.calibration_adjustment,
            'day5_rank': audit['finite_sample_rank'], 'day12_rank': new_audit[i]['rank'],
            'day5_bounds': [before.lower_bound,before.upper_bound], 'day12_bounds': [now.lower_bound,now.upper_bound],
            'day5_selected_origins': [k[1] for k in audit['selected_residual_keys']],
            'day12_selected_origins': [f'{o:%Y-%m}' for o in new_audit[i]['selected_source_origins']],
            'day5_scores': [r.calibration_score for r in sorted(old.released.values(),key=lambda r:r.residual_target_month)
                if r.source_model == raw.model_name and r.residual_horizon == i+1][-60:],
            'day12_scores': [v['scores'][i] for v in sorted(new.released.values(),key=lambda v:v['source_origin'])
                if v['model']==raw.model_name and v['scores'][i] is not None][-60:],
            'point_unchanged': before.point_prediction == now.point_prediction == raw.point_prediction})
    raw_rows = [{**r.record(), 'phase':'historical_train'} for b in batches for r in b.raw]
    vectors, counts = SavedOOFForecasts(raw_rows,p).vectors_as_of(store,evaluation,MODELS['sarimax'][0],60)
    new_vectors = new.vectors(MODELS['sarimax'][0],evaluation)
    joint_result = {'day6_vector_count':len(vectors), 'day12_vector_count':len(new_vectors),
        'origins_equal':[v.origin for v in vectors]==[v['source_origin'] for v in new_vectors],
        'ratios_equal':[v.ratios for v in vectors]==[v['ratios'] for v in new_vectors],
        'immature_or_missing_vectors':counts['future_or_immature'], 'paths_compared':0}
    if joint and len(vectors)>=24:
        seed = derived_seed(sc['planning_seed'],evaluation,current.raw[0].model_name,'planning')
        day6, _ = generate_joint_scenarios(vectors,current.points(),evaluation,current.raw[0].model_name,
            'planning',sc,p,Random(seed),seed)
        day12, _ = new.scenarios(current,'planning')
        joint_result.update(paths_compared=128, prices_equal=all(a.prices==b.prices for a,b in zip(day6.paths,day12.paths)),
            sampled_origins_equal=all(a.source_oof_origin==b.source_oof_origin for a,b in zip(day6.paths,day12.paths)),
            planning_seed=str(seed),
            pool_hash_equal=day6.pool_sha256==day12.pool_sha256,
            pool_hash_note='Different serialization/provenance schemas; compare semantic members/ratios, not digest equality')
        joint_result['path_pairs']=[{'source_origin':f'{a.source_oof_origin:%Y-%m}',
            'day6_prices':a.prices,'day12_prices':b.prices} for a,b in zip(day6.paths,day12.paths)]
    elif joint:
        try: new.scenarios(current,'planning')
        except ValueError: joint_result['insufficient_joint_rejected']=True
        else: raise AssertionError('Immature/insufficient joint pool accepted')
    last = origins[-1] if origins else None
    return {'origins':[f'{o:%Y-%m}' for o in origins], 'evaluation':f'{evaluation:%Y-%m}',
        'toy_no_fit':True, 'delayed_horizon':delayed_h, 'delay_seconds':delay_seconds,
        'last_origin_day5_released_horizons':sorted(r.residual_horizon for r in old.released.values()
            if r.residual_forecast_origin==last and r.source_model==MODELS['sarimax'][0]),
        'last_origin_day12_released':(MODELS['sarimax'][0],last) in new.released,
        'models_present':sorted({v['model'] for v in new.released.values()}),
        'horizons':horizons, 'joint':joint_result}


def counterexamples() -> list[dict]:
    o = date(2020,1,1)
    cases = []
    for name, evaluation, delayed, seconds in [
        ('h1_only',date(2020,3,1),None,1), ('h1_h2_only',date(2020,4,1),None,1),
        ('all_horizons',date(2020,5,1),None,1), ('late_h3_plus_one_second',date(2020,5,1),3,1),
        ('h3_at_exact_cutoff',date(2020,5,1),3,0), ('late_h1_blocks_vector',date(2020,5,1),1,1)]:
        cases.append({'case':name, **compare((o,),evaluation,delayed_h=delayed,delay_seconds=seconds,joint=True)})
    for n in (23,24,59,60,61):
        origins = tuple(add_months(date(2015,1,1),i) for i in range(n))
        cases.append({'case':f'pool_{n}',**compare(origins,date(2021,6,1),joint=True)})
    partial = date(2021,3,1)
    origins = tuple(add_months(date(2015,1,1),i) for i in range(23)) + (partial,)
    cases.append({'case':'fallback_divergence_23_plus_partial',**compare(origins,date(2021,6,1),joint=True)})
    origins = tuple(add_months(date(2015,1,1),i) for i in range(60)) + (partial,)
    cases.append({'case':'window_divergence_60_plus_partial',**compare(origins,date(2021,6,1),joint=True)})
    cases.append({'case':'unissued_origin_not_backfilled',**compare((),date(2020,5,1),joint=True)})
    cases.append({'case':'mixed_models_separate_pools',**compare(tuple(add_months(date(2015,1,1),i) for i in range(24)),date(2021,6,1),mixed=True,joint=True)})
    cases.append({'case':'crossing_excluded_from_scores_not_joint',**compare(tuple(add_months(date(2015,1,1),i) for i in range(24)),date(2021,6,1),invalid='crossing',joint=True)})
    return cases


def invalid_probes() -> list[dict]:
    permit = SessionPermit('DAY14_TOY_NO_FIT','DAY14_MANUAL_TOY_NOT_WORLD_BANK')
    pool = SequentialOOF(permit,config(5),config(6)['scenarios'],plan())
    store = SequentialObservationStore(permit);store.advance(date(2021,6,1));pool.tick(store,store.clock)
    result = []
    for kind in ('valid','crossing','inverted','nonfinite_bound','nonfinite_quantile','nonfinite_point','negative_bound'):
        b = toy_batch(store.clock,permit,invalid=kind)
        raw = b.raw[0]
        old, _ = calibrate(raw,(),plan(),config(5))
        # Nonfinite point cannot acquire the issuance digest (allow_nan=False), but calibrate currently accepts a direct object.
        new, _ = pool.calibrate(b)
        result.append({'case':kind,'raw_interval_usable':raw.interval_usable,'raw_crossing':raw.crossing,
            'raw_validity':raw.validity_status,'day5_status':old.calibration_status,'day12_status':new[0].calibration_status,
            'day5_output_usable':old.interval_usable,'day12_output_usable':new[0].interval_usable,
            'output_validity':new[0].validity_status,'base_nonfinite_or_missing':not all(
                v is not None and __import__('math').isfinite(v) for v in (raw.q10,raw.q50,raw.q90)),
            'point_preserved':(str(old.point_prediction)==str(new[0].point_prediction)==str(raw.point_prediction)),
            'native_publisher_would_reject':kind in ('nonfinite_bound','nonfinite_quantile','nonfinite_point','negative_bound'),
            'finding':'CR-02' if kind in ('nonfinite_quantile','nonfinite_point') else None})
    return result


def saved_synthetic_audit() -> tuple[dict,dict]:
    """Only saved Day12 SYNTHETIC issuance, residual and audit artifacts."""
    d = ROOT / D12
    manifest = read(d/'run_manifest.json')
    loaded = {}
    for name in ('calibrated.json.gz','calibration_audit.json.gz','oof_released.json.gz','oof_issue_log.json.gz','pool_audit.json.gz'):
        if sha(d/name)!=manifest['outputs'][name]:raise AssertionError('Day12 output changed: '+name)
        loaded[name] = read(d/name)
    batches = []
    for path in sorted((d/'issuances').glob('*.json')):
        value = read(path)
        key = path.relative_to(d).as_posix()
        if sha(path)!=manifest['outputs'][key]:raise AssertionError('Issuance file changed')
        batches.append(load_issued_forecast(path,value['issued_sha256']))
    raw = [r for b in batches for r in b.raw]
    corrected = loaded['calibrated.json.gz']
    lookup = {(b.raw[0].model_name,f'{b.origin:%Y-%m}',p.horizon):p for b in batches for p in b.raw}
    released = loaded['oof_released.json.gz']; calibration_audit = loaded['calibration_audit.json.gz']
    vectors = {(v['model'],v['source_origin']):v for v in released}
    corrected_keys = {(p['model_name'],p['forecast_origin'],p['horizon']) for p in corrected}
    crossings = []
    for b in batches:
        for p in b.raw:
            if not p.crossing:continue
            o = f'{b.origin:%Y-%m}'; key = p.model_name,o,p.horizon
            current = next((v for v in corrected if (v['model_name'],v['forecast_origin'],v['horizon'])==key),None)
            vector = vectors.get((p.model_name,o))
            if vector and vector['scores'][p.horizon-1] is not None:raise AssertionError('Crossing score included')
            uses = sum(o in a['selected_source_origins'] for a in calibration_audit if a['model']==p.model_name and a['horizon']==p.horizon)
            if uses:raise AssertionError('Crossing origin selected for same horizon')
            pool_uses = sum(any(v['source_origin']==o for v in a['vectors']) for a in loaded['pool_audit.json.gz'] if a['model']==p.model_name)
            crossings.append({'model':p.model_name,'origin':o,'horizon':p.horizon,'q10':p.q10,'q50':p.q50,'q90':p.q90,
                'raw_validity':p.validity_status,'issuance_sha256':b.digest,
                'phase':'historical_train' if b.origin<=date(2021,3,1) else 'validation' if b.origin<=date(2024,5,1) else 'final_shape_SYNTHETIC',
                'current_calibration_status':current['calibration_status'] if current else 'not_requested_historical',
                'same_horizon_score_uses':uses,'released_joint_vector':vector is not None,'joint_pool_memberships':pool_uses})
    for row in corrected:
        p = lookup[(row['model_name'],row['forecast_origin'],row['horizon'])]
        if row['point_prediction']!=p.point_prediction:raise AssertionError('Point changed')
        if p.crossing and (row['calibration_status']!='raw_invalid_uncalibrated' or row['lower_bound'] is not None or row['upper_bound'] is not None):
            raise AssertionError('Crossing laundered')
    # Independent counting from saved raw records; no performance metric is computed.
    audit = {'saved_synthetic_only':True,'issuance_batches':len(batches),'raw_rows':len(raw),
        'crossing_rows':len(crossings),'crossing_by_phase':dict(Counter(c['phase'] for c in crossings)),
        'current_calibration_rows':len(corrected),'calibration_status_counts':dict(Counter(p['calibration_status'] for p in corrected)),
        'point_unchanged_rows':len(corrected),'finite_raw_rows':sum(all(__import__('math').isfinite(v) for v in
            (p.point_prediction,p.q10,p.q50,p.q90,p.lower_bound,p.upper_bound)) for p in raw),
        'crossings':crossings,'synthetic_invalid_probes':invalid_probes(),
        'crossing_score_uses':0,'repair_or_clipping':False,'duplicate_crossing_keys':len(crossings)-len({(v['model'],v['origin'],v['horizon']) for v in crossings}),
        'note':'Repeated appearances in current calibration and later joint pools are linked lifecycle events, not extra unique crossing forecasts.'}
    proof_ok = all(json.loads(b.proof_json)['target_unobserved_at_issue'] and all(
        p.fit_information_end<=add_months(b.origin,-1) and p.fit_max_label_available_at<=decision_at(b.origin) for p in b.raw) for b in batches)
    issue_audit = {'saved_synthetic_only':True,'immutable_batch_hashes_verified':len(batches),'fit_timestamp_proofs_verified':proof_ok,
        'calendar_counts':dict(Counter('historical_train' if b.origin<=date(2021,3,1) else 'validation' if b.origin<=date(2024,5,1) else 'final_shape_SYNTHETIC' for b in batches)),
        'gap_2024_06_08_issuances':sum(date(2024,6,1)<=b.origin<=date(2024,8,1) for b in batches),
        'actual_seed_archive_adapter':'NOT_VERIFIED','actual_historical_contemporaneous_issuance':'NOT_VERIFIED',
        'actual_new_origin_native_fit':'NOT_VERIFIED','new_fits_in_day14':0,
        'restored_archive_contract':'externally pinned digest; exactly historical60+validation36 per model; source+knowledge+fit proof; no missing-origin refit',
        'provenance_levels':[
            {'kind':'Day5 historical OOF','evidence':'retrospective rolling fit/as-of proof and saved manifest','contemporaneous_live_issuance':False},
            {'kind':'Day5 validation forecasts/residuals','evidence':'saved retrospective prediction then evaluator release','contemporaneous_live_issuance':False},
            {'kind':'Day12 native synthetic','evidence':'236 immutable native batches; synthetic logical calendar and execution timestamps separate','actual_world_bank':False},
            {'kind':'future actual native origin','evidence':'API synthetic integration only; actual source and archive not connected','status':'NOT_VERIFIED'}]}
    return audit, issue_audit


def preservation(root: Path = ROOT) -> dict:
    baseline = read(root/'artifacts/day14/preservation_before.json')
    changed = [name for name,h in baseline['files'].items() if not (root/name).is_file() or sha(root/name)!=h]
    changed_data = []
    for name,s in baseline['data_stat_only'].items():
        p = root/name
        if not p.is_file() or p.stat().st_size!=s['size'] or p.stat().st_mtime_ns!=s['mtime_ns']:changed_data.append(name)
    return {'passed':not changed and not changed_data,'prior_file_hashes_checked':len(baseline['files']),
        'data_metadata_only_checked':len(baseline['data_stat_only']),'changed_files':changed,'changed_data_metadata':changed_data,
        'data_bytes_opened_or_rehashed':False}


def verify_upstream() -> dict:
    assert sha(ROOT/CANDIDATE)==CANDIDATE_SHA and sha(ROOT/RELEASE)==RELEASE_SHA
    release = read(ROOT/RELEASE)
    for name,h in release['outputs'].items():assert sha((ROOT/RELEASE).parent/name)==h
    for row in release['references']:
        path = (ROOT/row['path']).resolve()
        assert path.is_relative_to(ROOT) and not path.is_relative_to(ROOT/'data')
        assert sha(path)==row['sha256'] and path.stat().st_size==row['size_bytes']
    candidate = read(ROOT/CANDIDATE)
    # Check non-data pins only; do not call the full verifier which opens synthetic data.
    mismatch = [name for group in ('contract_files','code_files','metadata_files')
        for name,h in candidate[group].items() if sha(ROOT/name)!=h]
    return {'candidate_sha256':CANDIDATE_SHA,'day13_release_sha256':RELEASE_SHA,
        'day13_references_checked':len(release['references']),'day13_outputs_checked':len(release['outputs']),
        'candidate_pinned_mismatches':mismatch,'candidate_file_preserved':True,
        'candidate_authorizes_day14':False,'old_approval_reuse_allowed':False,
        'candidate_synthetic_input_bytes_rechecked':False,'holdout_execution_allowed':False}


def contract_matrix() -> list[dict]:
    return [{'field':field,'day5':a,'day12':b,'assessment':result} for field,a,b,result in [
        ('Forecast Origin','issued raw origin o < t','immutable issued batch o < t','same calendar; different provenance envelope'),
        ('Target Horizon','h=1,2,3; target=o+h','h=1,2,3; target=o+h','same'),
        ('Actual Availability Cutoff','o+h<=t-1 AND available_at(o+h)<=d_t','o+3<=t-1 AND ALL available_at(o+j)<=d_t','different for H1/H2; delayed H1/H2 can delay H3 too'),
        ('Calibration Residual Release Time','first visited eligible clock per horizon','first visited full-vector eligible clock','intentional Day12-local override, unresolved final protocol conflict'),
        ('OOF Pool Membership','valid raw interval + finite point; same model/h/method','full vector; score None for invalid interval; select same model/h/method','joint membership independent of raw interval validity'),
        ('Pool Window / Minimum','recent 60 eligible scores per model/h; minimum24','recent60 non-None scores per model/h; minimum24','same window after different release filter'),
        ('Finite-Sample Quantile Rank','ceil((n+1)*.8), 1-based, no interpolation','same function, hard-coded .8','same; coverage contract currently .8'),
        ('Fallback','n<24 or k>n => insufficient_raw_fallback; invalid raw => raw_invalid_uncalibrated','same','raw_invalid is NOT successful fallback; no fit/scenario/solver fallback'),
        ('Point Forecast','replace interval fields only','replace interval fields only','point invariant'),
        ('Joint Scenario Connection','Day6 independently constructs full vectors from raw point/actual','ratios=actual/raw point; calibrate output not used by scenarios','no direct interval-to-scenario edge'),
    ]]


def readiness() -> list[dict]:
    return [
        {'state':'MVP_COMPLETE','status':'PASS','basis':'Day13 unchanged 5/5 saved-evidence acceptance'},
        {'state':'TECHNICAL_READY','status':'PASS','basis':'Day12 unchanged 19/19 synthetic integration; historical scoped evidence, not refreshed actual-source readiness'},
        {'state':'METHODOLOGY_CONSISTENT','status':'ACTION_REQUIRED','basis':'CR-01 final calibration precedence; CR-02 finite validation contract'},
        {'state':'SOURCE_PROVENANCE_VERIFIED','status':'NOT_VERIFIED','basis':'snapshot documented; historical vintage/release/live issuance/actual archive connection unverified'},
        {'state':'PUBLICATION_MATURE','status':'NOT_VERIFIED','basis':'actual last-target release not verified; assumed threshold 2026-10-31T23:59:59Z; no synthetic clock or current date promotion'},
        {'state':'USER_AUTHORIZED','status':'false','basis':'Day14 audit only; no digest-bound evaluation approval'},
        {'state':'HOLDOUT_EXECUTION_ALLOWED','status':'false','basis':'locked; no real capability or approval; conjunction of required gates not satisfied'},
    ]


def build(output: Path) -> dict:
    output = output.resolve()
    if not output.is_relative_to(ROOT/'artifacts/day14'):raise ValueError('Day14 output folder required')
    output.mkdir(parents=True,exist_ok=False)
    with no_data_access(ROOT) as access:
        upstream = verify_upstream()
        cases = counterexamples()
        crossing, issuance = saved_synthetic_audit()
        documents = ['docs/DAY14_METHOD_CONSISTENCY.md','docs/DAY14_SOURCE_PROVENANCE_AUDIT.md','docs/DAY14_STATUS.md']
        matrix = contract_matrix()
        save(output/'calibration_contract_difference_matrix.json',matrix)
        save(output/'synthetic_maturity_counterexamples.json',cases)
        save(output/'quantile_crossing_fallback_audit.json',crossing)
        save(output/'oof_issuance_seed_provenance_audit.json',issuance)
        save(output/'readiness_matrix.json',readiness())
        save(output/'upstream_integrity.json',upstream)
        save(output/'source_provenance_matrix.json',[
            {'item':'official snapshot identity','status':'DOCUMENTED_PRIOR_EVIDENCE','basis':'docs/WORLD_BANK_SOURCE.md; 2026-10-24 retrieval; official URL; nominal USD/metric tonne; raw SHA ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154','raw_reopened_today':False},
            {'item':'latest revised snapshot','status':'DOCUMENTED_PRIOR_EVIDENCE','basis':'one collection vintage; published revision comments; not first releases'},
            {'item':'historical per-release vintages','status':'NOT_VERIFIED','basis':'no historical vintage archive held'},
            {'item':'actual historical release timestamp per observation','status':'NOT_VERIFIED','basis':'HTTP modified/workbook update/retrieval are different from observation release'},
            {'item':'project available_at','status':'ASSUMPTION','basis':'next-month-end UTC; observation<=t-1 AND timestamp<=decision; pseudo-real-time'},
            {'item':'2020-07 HRW definition boundary','status':'DOCUMENTED_PRIOR_EVIDENCE','basis':'no.1 through June2020, no.2 thereafter; no proven structural break'},
            {'item':'Day12 synthetic issuance timestamp','status':'VERIFIED_SYNTHETIC_ONLY','basis':'logical calendar+immutable batch+fit proof; not historical actual live issuance'},
            {'item':'actual final native source/seed integration','status':'NOT_VERIFIED','basis':'real source remains disabled; no source or forecast fit today'},
        ])
        save(output/'final_evaluation_methodology_impact.json',{
            'point_forecasts':'unchanged under calibration-release-only change',
            'calibration_intervals':'can differ; fallback 24 vs23 and rolling-window/rank examples recorded',
            'joint_scenario_pool':'full-vector in BOTH Day6/12; invalid intervals do not exclude valid point-error ratios',
            'planning_rn_ra':'no interval input; same members/ratios/seed/current raw points => same 128 prices; seven toy comparisons recorded',
            'cvar':'formula alpha=.9/lambda0,.5 unchanged; no direct calibration edge; could differ if point/pool/seed or failure gating changed later',
            'fa_vs_ra':'FA consumes point, RA consumes raw-point ratio joint paths; comparison is not pure calibration or pure CVaR effect',
            'validation_holdout_comparability':'interval methodology NOT identical until CR-01 resolved; cost-input path not automatically changed',
            'additional_scenario_validity_condition':'proposed complete-interval validity filter would CHANGE pool and policy inputs; must not add silently',
            'actual_performance_remeasured':False,'policy_solver_invoked':False,'operating_metrics_settings_changed':False})
        save(output/'methodological_decision_record.json',{
            'status':'PROPOSED_NOT_IMPLEMENTED','decision_id':'DAY14-MDR-01',
            'precedence':'Day5 original statistical specification; Day11 calibration_spec points to Day5; Day12 explicitly overrides locally for synthetic integration, not final statistical approval',
            'recommended':'restore horizon-specific calibration release in a future approved adapter change; retain full-vector joint release',
            'selection_basis':'pre-specified methodological compatibility, NOT validation performance',
            'options':[
                {'id':'A','rule':'Day5 horizon calibration + full-vector joint','compatibility':'preserves Day5 calibration/Day6 joint; changes Day12 adapter','refreeze_required':True,'recommended':True},
                {'id':'B','rule':'full-vector calibration + joint','compatibility':'preserves Day12 integration; changes Day5 interval estimand and delay/window','refreeze_required':True,'recommended':False},
                {'id':'C','rule':'leave both and label separate sensitivity protocols','compatibility':'preserves archives but does not define a single final primary uncertainty protocol','refreeze_required':True,'recommended':False}],
            'change_requests':[
                {'id':'CR-01','status':'ACTION_REQUIRED','proposal':'decouple per-horizon calibration release from vector joint release; retain immutable issuance/source/phase/actual availability and recent60/min24 guards; regenerate only approved synthetic evidence before new freeze'},
                {'id':'CR-02','status':'ACTION_REQUIRED','proposal':'define raw prediction usability separately for point, interval and quantile; reject nonfinite quantile/point before score/calibration across legacy and sequential APIs; preserve negative finite bounds/crossing facts; explicit tests; no automatic clipping'},
                {'id':'CR-03','status':'NOT_VERIFIED','proposal':'authorize and verify actual saved seed provenance adapter separately; retrospective OOF must not be called contemporaneous live issuance; never fill Jun-Aug2024 gaps'}],
            'approval_requested_or_granted_today':False,'production_code_changed':False,'old_freeze_reused_for_approval':False})
        preserved = preservation()
        if not preserved['passed']:raise AssertionError('Prior output changed')
        save(output/'preservation.json',preserved)
        save(output/'source_access_audit.json',access)
        references = ['AGENTS.md','configs/day5.toml','configs/day6.toml','configs/day11.toml','configs/day12.toml',CANDIDATE,RELEASE,
            D12+'/run_manifest.json',D12+'/calibrated.json.gz',D12+'/oof_released.json.gz',D12+'/calibration_audit.json.gz',D12+'/pool_audit.json.gz',
            'src/food_procurement_intelligence/uncertainty/calibration.py','src/food_procurement_intelligence/uncertainty/sequential.py',
            'src/food_procurement_intelligence/uncertainty/joint_scenarios.py','src/food_procurement_intelligence/uncertainty/contracts.py',
            'src/food_procurement_intelligence/forecasting/publisher.py','src/food_procurement_intelligence/evaluation/sequential_runner.py',
            'docs/DAY5_UNCERTAINTY_DESIGN.md','docs/DAY6_DESIGN.md','docs/DAY11_PRE_HOLDOUT_PROTOCOL.md','docs/DAY11_RELEASE_GATE.md',
            'docs/DAY11_LIMITATIONS.md','docs/DAY12_PRODUCTION_INTEGRATION.md','docs/DAY12_STATUS.md','docs/DAY13_STATUS.md',
            'docs/MVP_ACCEPTANCE_REPORT.md','docs/REPRODUCIBILITY.md','docs/WORLD_BANK_SOURCE.md',*documents,
            'scripts/day14/audit.py','scripts/day14/verify.py','scripts/day14/run_tests.py','tests/test_day14_methodology.py']
        manifest = {'kind':'DAY14_READ_ONLY_METHODOLOGY_AUDIT_NOT_EVALUATION_FREEZE','actual_holdout_execution_allowed':False,
            'holdout_locked':True,'production_code_changed':False,'new_forecast_fits':0,
            'outputs':{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()},
            'references':{name:sha(ROOT/name) for name in references}}
        save(output/'audit_manifest.json',manifest)
    return {'output':str(output.relative_to(ROOT)),'counterexamples':len(cases),'crossings':crossing['crossing_rows'],
        'manifest_sha256':sha(output/'audit_manifest.json'),'source_access':access}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output),ensure_ascii=False))
