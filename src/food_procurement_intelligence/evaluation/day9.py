"""Frozen historical-price simulated procurement evaluation, Holdout still locked."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
import sys
import tomllib

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.evaluation.day6 import _serializable
from food_procurement_intelligence.evaluation.historical_prices import GuardedValidationPrices, HistoricalEvaluationWorld
from food_procurement_intelligence.evaluation.model_backtesting import digest, save_csv, save_json
from food_procurement_intelligence.evaluation.policy_backtest import run_historical_policy, period_metrics, paired_comparison
from food_procurement_intelligence.evaluation.policy_inputs import PreparedPolicyInputs, make_policy, record_hash
from food_procurement_intelligence.evaluation.splits import load_split_plans, months_between, parse_month_label
from food_procurement_intelligence.optimization.forecast_adapter import load_point_adapter
from food_procurement_intelligence.optimization.scenario_adapter import SavedPlanningScenarios
from food_procurement_intelligence.simulation.contracts import SimulationSettings, Supplier


POLICIES=('fixed','fa_sarimax','rn_sarimax','ra_sarimax','fa_lightgbm','rn_lightgbm','ra_lightgbm')
PAIRS=(('fa_sarimax_minus_fixed','fa_sarimax','fixed'),('ra_sarimax_minus_fa','ra_sarimax','fa_sarimax'),
       ('ra_sarimax_minus_rn','ra_sarimax','rn_sarimax'),('rn_sarimax_minus_fa','rn_sarimax','fa_sarimax'),
       ('fa_lightgbm_minus_fixed','fa_lightgbm','fixed'),('ra_lightgbm_minus_fa','ra_lightgbm','fa_lightgbm'),
       ('ra_lightgbm_minus_rn','ra_lightgbm','rn_lightgbm'),('rn_lightgbm_minus_fa','rn_lightgbm','fa_lightgbm'),
       ('fa_model_change','fa_lightgbm','fa_sarimax'),('rn_model_change','rn_lightgbm','rn_sarimax'),
       ('ra_model_change','ra_lightgbm','ra_sarimax'))


def protected_files(root: Path) -> int:
    import hashlib
    data=json.loads((root/'artifacts/day9/preservation_before.json').read_text(encoding='utf-8'))
    for name,expected in data['sha256'].items():
        if digest(root/name)!=expected: raise ValueError('Old result changed: '+name)
    for name,info in data['append_only'].items():
        if hashlib.sha256((root/name).read_bytes()[:info['bytes']]).hexdigest()!=info['sha256']:
            raise ValueError('Old document prefix changed: '+name)
    return len(data['sha256'])


def load_day9(path: Path):
    config=tomllib.loads(path.read_text(encoding='utf-8'))
    root=(path.resolve().parent/config['project_root']).resolve()
    for key in ('day8_config','split_config','report_root','synthetic_root'):
        if not (root/config[key]).resolve().is_relative_to(root): raise ValueError('Path escaped root')
    if config['holdout_locked'] is not True or config['schema_version']!=1:
        raise ValueError('Unsupported or unlocked protocol')
    for file,key in (('day8_config','day8_config_sha256'),('split_config','split_sha256')):
        if digest(root/config[file])!=config[key]: raise ValueError('Frozen upstream config changed')
    freeze=json.loads((root/'artifacts/day9/protocol_freeze.json').read_text(encoding='utf-8'))
    if digest(path)!=freeze['config_sha256'] or digest(root/'docs/DAY9_EVALUATION_PROTOCOL.md')!=freeze['protocol_sha256']:
        raise ValueError('Day 9 protocol changed after freeze')
    gate=json.loads((root/'artifacts/day9/toy_gate.json').read_text(encoding='utf-8'))
    if gate['exit_code']!=0 or gate['passed']<21: raise ValueError('Toy gate did not pass')
    for name,expected in gate['sha256'].items():
        if digest(root/name)!=expected: raise ValueError('Toy-verified implementation changed')
    if tuple(config['evaluation']['policies'])!=POLICIES: raise ValueError('Policy comparison changed')
    plan,_=load_split_plans(root/config['split_config'])
    c=config['calendar']
    for key,value in (('initial_state_at',plan.validation_origin_start),('first_decision',plan.validation_origin_start),
        ('last_decision',plan.validation_origin_end),('first_ledger',plan.validation_target_start),
        ('last_ledger',plan.validation_target_end),('active_ledger_end',plan.validation_origin_end)):
        if parse_month_label(c[key])!=value: raise ValueError('Evaluation calendar differs from frozen split')
    protected_files(root)
    d8=tomllib.loads((root/config['day8_config']).read_text(encoding='utf-8'))
    d7=tomllib.loads((root/d8['day7_config']).read_text(encoding='utf-8'))
    d6=tomllib.loads((root/d7['day6_config']).read_text(encoding='utf-8'))
    return root,config,plan,d8,d7,d6


def run_day9(path: Path) -> dict:
    root,config,plan,d8,d7,d6=load_day9(path)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=root/config['report_root']/run_id
    synthetic=root/config['synthetic_root']/run_id
    directory.mkdir(parents=True,exist_ok=False); synthetic.mkdir(parents=True,exist_ok=False)
    save_json(directory/'spec_freeze.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'config':config,
        'config_sha256':digest(path),'protocol_sha256':digest(root/'docs/DAY9_EVALUATION_PROTOCOL.md'),'evaluation_started':False})
    settings=SimulationSettings(**{key:d6['simulation'][key] for key in SimulationSettings.__dataclass_fields__})
    suppliers=tuple(Supplier(**row) for row in d6['suppliers'])
    origins=months_between(plan.validation_origin_start,plan.validation_origin_end)
    models={'sarimax':d8['models'][0],'lightgbm':d8['models'][1]}
    results,policies={},{}
    complete=False
    timings=[]
    try:
        adapters={label:load_point_adapter(root/d7[label+'_run'],plan,model) for label,model in models.items()}
        scenarios=SavedPlanningScenarios(root/d8['day6_run'],root,plan,d8['day6_manifest_sha256'])
        inputs=PreparedPolicyInputs(origins,models,adapters,scenarios)
        save_json(directory/'input_availability_audit.json',_serializable(inputs.audit))
        store=load_development_store(root,root/'configs/day2.toml')
        evaluator=GuardedValidationPrices(store.validation_actuals_reader(),plan)
        prices=evaluator.frozen_path()
        world=HistoricalEvaluationWorld(config['operations']['world_id'],plan.validation_target_start,plan.validation_target_end,
            prices,tuple((p.month,config['operations']['demand_tonnes_per_month']) for p in prices))
        save_json(synthetic/'operations.json',_serializable({'world_id':world.scenario_id,'settings':asdict(settings),
            'suppliers':[asdict(s) for s in suppliers],'initial_pipeline':[],
            'realized_demands':world.realized_demands,'delays':world.delays,
            'evaluation_seed_bank':config['operations']['evaluation_seed_bank'],'operations_are_synthetic':True}))
        save_csv(directory/'evaluation_prices.csv',[{'observation_month':p.month.strftime('%Y-%m'),'price':p.price,
            'unit':p.unit,'available_at':p.available_at.isoformat(),'availability_basis':'assumed_month_plus_one_month_end',
            'vintage_id':'20261024T012917500704Z_ea1c35082787','usage':'evaluator_only'} for p in prices])
        save_json(directory/'evaluation_reader_audit.json',{'unique_requests':evaluator.requests,'request_count':len(evaluator.requests),
            'bridge_holdout_requested':False,'policy_has_evaluation_reader':False,'world_sha256':record_hash(asdict(world))})
        for name in POLICIES:
            policy=make_policy(name,inputs,settings,d7['lp'],d8['risk'],plan.validation_origin_end)
            policies[name]=policy
            result=run_historical_policy(world,settings,suppliers,policy,plan.validation_origin_start,plan.validation_origin_end,store.history_as_of)
            results[name]=result
            save_json(directory/(name+'_decision_audit.json'),_serializable(result['decision_audit']))
            save_json(directory/(name+'_rolling_plans.json'),_serializable(getattr(policy,'history',[])))
            save_json(directory/(name+'_runoff.json'),result['runoff_no_action'])
            for kind in ('ledger','orders','receipts'):
                save_csv(directory/(name+'_'+kind+'.csv'),_serializable(result[kind]))
            for i,solution in enumerate(getattr(policy,'solutions',[])):
                if solution.lp_text: (directory/(name+f'_{i+1:02d}.lp')).write_text(solution.lp_text,encoding='utf-8')
                timings.append({'policy':name,'origin':origins[i].strftime('%Y-%m'),'status':solution.status,'solve_seconds':solution.solve_seconds})
            if not result['complete']:
                save_json(directory/'failure.json',_serializable({'policy':name,**result['failure'],
                    'unattempted_policies':[p for p in POLICIES if p not in results],
                    'full_period_comparison_available':False,'partial_decision_history_saved':True}))
                break
        complete=len(results)==len(POLICIES) and all(r['complete'] for r in results.values())
        if complete:
            metrics=[]
            for name,result in results.items():
                supplier_orders={s.supplier_id:math.fsum(o['quantity_tonnes'] for o in result['orders'] if o['supplier_id']==s.supplier_id) for s in suppliers}
                for period in ('full','active','runoff'):
                    row=period_metrics(result,period,suppliers)
                    metrics.append({'policy':name,**row,'orders_by_supplier_all_decisions':supplier_orders,
                        'initial_inventory':200.,'initial_pipeline':0.,'terminal_outstanding_tonnes':result['summary']['terminal_outstanding_tonnes'],
                        'optimal_solves':sum(s.status=='OPTIMAL' for s in getattr(policies[name],'solutions',[])),
                        'fixed_decisions':36 if name=='fixed' else 0,'runoff_no_action':len(result['runoff_no_action']),
                        'failure_count':0,'fallback_count':0})
            save_json(directory/'policy_metrics.json',metrics); save_csv(directory/'policy_metrics.csv',metrics)
            monthly,paired=paired_comparison(results,PAIRS)
            save_csv(directory/'paired_monthly.csv',_serializable(monthly)); save_json(directory/'paired_summary.json',paired)
            order_deltas=[]
            for label,left,right in PAIRS:
                for origin in origins:
                    row={'comparison':label,'origin':origin}
                    for supplier in suppliers:
                        quantities=[math.fsum(o['quantity_tonnes'] for o in results[n]['orders'] if o['order_month']==origin and o['supplier_id']==supplier.supplier_id) for n in (left,right)]
                        row[supplier.supplier_id+'_order_difference']=quantities[0]-quantities[1]
                    order_deltas.append(row)
            save_csv(directory/'paired_decision_orders.csv',_serializable(order_deltas))
            horizon_receipts=[]
            for name,result in results.items():
                for receipt in result['receipts']:
                    offset=(receipt['receipt_month'].year-receipt['order_month'].year)*12+receipt['receipt_month'].month-receipt['order_month'].month
                    horizon_receipts.append({'policy':name,'order_id':receipt['order_id'],'order_origin':receipt['order_month'],
                        'receipt_month':receipt['receipt_month'],'actual_delivery_offset':offset,
                        'quantity':receipt['quantity_tonnes'],'procurement_cost':receipt['procurement_cost']})
            save_csv(directory/'receipt_horizon_audit.csv',_serializable(horizon_receipts))
    except Exception as error:
        complete=False
        save_json(directory/'failure.json',{'stage':'preflight_or_engine_evaluation','error_type':type(error).__name__,
            'error':str(error),'first_failure_origin':getattr(error,'origin',None),
            'completed_policies':list(results),'full_period_comparison_available':False,'fallback':None})
    completeness={'complete':complete,'expected_policies':list(POLICIES),'completed_policies':[n for n,r in results.items() if r['complete']],
        'per_policy':{n:{'complete':r['complete'],'decisions':len(r['decision_audit']),'ledger_months':len(r['ledger']),
            'failure':r['failure']} for n,r in results.items()},'full_period_comparison_available':complete}
    if complete:
        completeness['confirmed_common_ledger_through']=plan.validation_target_end
    else:
        endpoints=[r['failure']['confirmed_ledger_through'] for r in results.values() if not r['complete']]
        completeness['confirmed_common_ledger_through']=min(endpoints) if endpoints and all(endpoints) else None
    save_json(directory/'completeness.json',_serializable(completeness)); save_json(directory/'solver_timing.json',timings)
    protected_files(root)
    from ortools.linear_solver import _pywraplp
    package=root/'src/food_procurement_intelligence'
    sources=[Path(__file__),*[package/'evaluation'/n for n in ('historical_prices.py','policy_backtest.py','policy_inputs.py')],
        package/'optimization/order_calendar.py',root/'scripts/verify_day9_results.py']
    upstream=json.loads((root/d8['day6_run']/'manifest.json').read_text(encoding='utf-8'))
    outputs={p.relative_to(root).as_posix():digest(p) for parent in (directory,synthetic) for p in sorted(parent.iterdir()) if p.is_file()}
    save_json(directory/'manifest.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'config':config,'config_sha256':digest(path),
        'toy_gate_sha256':digest(root/'artifacts/day9/toy_gate.json'),
        'protocol_freeze_sha256':digest(root/'artifacts/day9/protocol_freeze.json'),
        'preservation_snapshot_sha256':digest(root/'artifacts/day9/preservation_before.json'),
        'protocol_sha256':digest(root/'docs/DAY9_EVALUATION_PROTOCOL.md'),'source_data':upstream['source_data'],'raw_sha256':upstream['raw_sha256'],
        'source_links':{name:digest(root/name) for name in ('configs/splits.toml','configs/day8.toml',d8['day6_run']+'/manifest.json',
            d7['sarimax_run']+'/manifest.json',d7['lightgbm_run']+'/manifest.json','artifacts/day8/20261030T070224306255Z/manifest.json')},
        'python':sys.version,'versions':{n:version(n) for n in ('ortools','numpy','pandas','statsmodels','lightgbm','protobuf')},
        'solver_extension_sha256':digest(Path(_pywraplp.__file__)),'code_sha256':{p.relative_to(root).as_posix():digest(p) for p in sources},
        'output_sha256':outputs,'synthetic_directory':synthetic.relative_to(root).as_posix(),'complete':complete,
        'holdout_locked':True,'bridge_used':False,'vintage_mode':'latest_vintage_pseudo_real_time',
        'experiment_name':config['experiment_name'],'independent_oos_claim':False,'market_cvar_estimated':False})
    return {'report_dir':directory.relative_to(root).as_posix(),'complete':complete,
        'full_metrics':[r for r in metrics if r['period']=='full'] if complete else None}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/day9.toml'))
    args=parser.parse_args()
    output=run_day9(args.config)
    print(json.dumps(output,indent=2))
    if not output['complete']: raise SystemExit(1)
