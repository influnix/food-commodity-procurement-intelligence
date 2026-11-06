"""Pinned synthetic final runner dress rehearsal; no actual source or new fit."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
import argparse
from collections import Counter
from dataclasses import asdict,replace
from datetime import date
import json
from pathlib import Path
from unittest.mock import patch

from scripts.compatibility.handoff_support import ROOT,D12,cfg,read,save,zipped,sha,no_data_access,load_saved_batches,preservation
from food_procurement_intelligence.data.sequential import canonical_hash,SessionPermit,SequentialObservationStore
from food_procurement_intelligence.evaluation.final_contract import prepare_final_synthetic_stream,FINAL_CALENDAR
from food_procurement_intelligence.evaluation.sequential_runner import synthetic_observations,release_publications,run_policy_calendar
from food_procurement_intelligence.evaluation.splits import load_split_plans
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.evaluation.model_backtesting import save_csv
from food_procurement_intelligence.evaluation.policy_inputs import PreparedPolicyInputs,make_policy
from food_procurement_intelligence.evaluation.historical_backtest import POLICIES
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher
from food_procurement_intelligence.simulation.contracts import DecisionContext,SimulationSettings,Supplier

D15=ROOT/'artifacts/day15/evidence_a'


class SavedSyntheticPublisher:
    """Replay pre-existing native batches; never claims fresh historical issuance."""
    def __init__(self,d4,candidates,directory=None):
        if directory is not None:raise ValueError('Replay does not emit replacement native issuances')
        self.batches=load_saved_batches();self.events=[];self.seen=set();self.calls=[]

    def publish(self,store,origin):
        if store.clock!=origin or origin in self.seen:raise ValueError('Replay clock/duplicate issuance')
        result=[]
        for label in ('sarimax','lightgbm'):
            batch=self.batches.get((label,origin))
            if batch is None:raise LookupError('Previously unissued forecast; no backfill')
            proof=json.loads(batch.proof_json)
            if (proof['source_id']!=store.permit.source_id or proof['source_session']!=store.permit.session_id
                or proof['history_sha256']!=canonical_hash([p.__dict__ for p in store.history_as_of(origin)])):
                raise ValueError('Replay original source/history proof mismatch')
            result.append(batch)
        self.seen.add(origin);self.calls.append(origin)
        return tuple(result)


def prepare():
    plan=load_split_plans(ROOT/'configs/evaluation/splits.toml')[0]
    stream=prepare_final_synthetic_stream(cfg(12),cfg(4),cfg(5),cfg(6),plan,synthetic_observations(cfg(12)),publisher_factory=SavedSyntheticPublisher)
    assert stream['final_wiring']['calibration_adapter']=='HorizonSequentialOOF'
    assert not stream['events'],'No new native fitting events allowed'
    return stream


def future_mutation_prefix(stream) -> dict:
    """Required leakage probe only: mutate unpublished inputs, compare first orders; no new stress performance."""
    o=FINAL_CALENDAR.first_origin;observations=stream['observations']
    changed=tuple(replace(p,price=p.price+1.) if p.observation_month>=o else p for p in observations)
    stores=[]
    for values in (observations,changed):
        s=SequentialObservationStore(SessionPermit('DAY12_NATIVE_STREAM_V1',values[0].source_id))
        release_publications(s,values,o);stores.append(s)
    assert stores[0].history_as_of(o)==stores[1].history_as_of(o)
    d4,d6=cfg(4),cfg(6);models={k:d4[k]['model_name'] for k in ('sarimax','lightgbm')}
    inputs=PreparedPolicyInputs((o,),models,{label:(lambda t,label=label:stream['issued'][label,t].points()) for label in models},
        lambda t,m:stream['scenarios'][next(k for k,v in models.items() if v==m),t])
    settings=SimulationSettings(**{k:d6['simulation'][k] for k in SimulationSettings.__dataclass_fields__})
    suppliers=tuple(Supplier(**r) for r in d6['suppliers']);checked=[]
    for name in POLICIES:
        orders=[]
        for s in stores:
            ctx=DecisionContext(o,FINAL_CALENDAR.last_ledger,200.,100.,suppliers,(),s.history_as_of(o))
            policy=make_policy(name,inputs,settings,cfg(7)['lp'],cfg(8)['risk'],FINAL_CALENDAR.last_origin)
            orders.append([asdict(v) for v in policy(ctx)])
        assert orders[0]==orders[1]
        checked.append({'policy':name,'same_first_orders':True})
    return {'passed':True,'unpublished_records_mutated':sum(p.observation_month>=o for p in observations),
        'history_and_fixed_forecast_input_unchanged':True,'first_origin':f'{o:%Y-%m}','policies':checked,
        'new_stress_world_or_performance_evaluation':False}


def run(output:Path) -> dict:
    output=output.resolve()
    if not output.is_relative_to(ROOT/'artifacts/day16'):raise ValueError('Day16 output only')
    output.mkdir(parents=True,exist_ok=False)
    code={p.relative_to(ROOT).as_posix():sha(p) for top in ('src','configs','scripts/compatibility') for p in sorted((ROOT/top).rglob('*')) if p.is_file() and p.suffix in ('.py','.toml','.json')}
    with no_data_access(ROOT) as access,patch.object(NativeForecastPublisher,'publish',side_effect=AssertionError('No new fit')):
        stream=prepare();save(output/'final_wiring.json',stream['final_wiring'])
        # The final wrapper uses the same corrected lifecycle as Day15's verified replay.
        for key in ('calibrated','calibration_audit','pool_audit','oof_released'):
            values=_serializable(stream[key]);assert values==read(D15/(key+'.json.gz')),key+' changed'
            zipped(output/(key+'.json.gz'),values)
        save(output/'synthetic_observations.json',[asdict(p) for p in stream['observations']])
        save(output/'future_mutation_prefix.json',future_mutation_prefix(stream))
        r=run_policy_calendar(stream,FINAL_CALENDAR,cfg(4),cfg(6),cfg(7),cfg(8))
        if not r['complete']:raise RuntimeError('Final synthetic E2E incomplete; full comparison forbidden')
        target=output/'final_shape';target.mkdir()
        save(output/'final_shape_operations.json',{'settings':r['settings'],'suppliers':r['suppliers'],
            'knowledge_type':'synthetic_day12_not_world_bank','demand':100.,'realized_extra_delay':0,'initial_pipeline':[]})
        files_equal=0
        for name,v in r['results'].items():
            for kind in ('ledger','orders','receipts'):
                path=target/(name+'_'+kind+'.csv');save_csv(path,_serializable(v[kind]))
                if path.read_bytes()!=(D15/'final_shape'/path.name).read_bytes():raise ValueError('Final policy flow changed: '+path.name)
                files_equal+=1
            save(target/(name+'_decision_audit.json'),v['decision_audit']);save(target/(name+'_runoff.json'),v['runoff_no_action'])
            zipped(target/(name+'_plans.json.gz'),r['plans'][name])
            assert read(target/(name+'_plans.json.gz'))==read(D15/'final_shape'/(name+'_plans.json.gz'))
        for name in ('metrics','monthly','paired','input_audit','calendar'):
            save(target/(name+'.json'),r[name]);assert read(target/(name+'.json'))==read(D15/'final_shape'/(name+'.json'))
        statuses=Counter(p['calibration_status'] for p in stream['calibrated'])
        summary={'complete':True,'decision_origins':22,'ledger_months':24,'policies':7,
            'decision_records':sum(len(v['decision_audit']) for v in r['results'].values()),
            'ledger_rows':sum(len(v['ledger']) for v in r['results'].values()),'optimal_lp_plans':r['optimal_solves'],
            'byte_equal_day15_flow_files':files_equal,'day15_final_plans_metrics_equal':True,
            'new_forecast_fits':0,'actual_holdout_execution_allowed':False,'source_kind':'synthetic_day12_not_world_bank'}
        assert (summary['decision_records'],summary['ledger_rows'],summary['optimal_lp_plans'])==(154,168,132)
        save(output/'dress_summary.json',summary)
        save(output/'failure_fallback_audit.json',{'fit_failure':0,'fit_mode':'pinned synthetic native replay; no fit',
            'calibration_status_counts':dict(statuses),'joint_failure':0,'solver_failure':0,'hidden_fallback':0,
            'policy_failure':{},'incomplete_comparison_allowed':False})
        p=preservation();assert p['passed'];save(output/'preservation.json',p);save(output/'source_access_audit.json',access)
        assert all(sha(ROOT/n)==h for n,h in code.items()),'Code changed during rehearsal'
        save(output/'run_manifest.json',{'kind':'DAY16_FINAL_SYNTHETIC_DRESS_REHEARSAL','complete':True,'code_at_start':code,
            'outputs':{p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
            'actual_holdout_execution_allowed':False,'holdout_locked':True,'new_forecast_fits':0})
    return {'output':output.relative_to(ROOT).as_posix(),'summary':summary,'source_access':access}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(run(a.output)))
    except Exception as e:
        if a.output.is_dir():save(a.output/'failure.json',{'complete':False,'full_comparison_allowed':False,'error_type':type(e).__name__,'error':str(e)})
        raise
