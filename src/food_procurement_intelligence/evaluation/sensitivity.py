"""Day 10 cell adapters, unchanged policy/engine execution and stability metrics."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.evaluation.day6 import _serializable
from food_procurement_intelligence.evaluation.day9 import load_day9, POLICIES, PAIRS
from food_procurement_intelligence.evaluation.historical_prices import GuardedValidationPrices, HistoricalEvaluationWorld
from food_procurement_intelligence.evaluation.model_backtesting import digest, save_csv, save_json
from food_procurement_intelligence.evaluation.policy_backtest import run_historical_policy, period_metrics, paired_comparison, COST_KEYS
from food_procurement_intelligence.evaluation.policy_inputs import PreparedPolicyInputs, make_policy, record_hash
from food_procurement_intelligence.evaluation.splits import months_between, parse_month_label
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.optimization.forecast_adapter import load_point_adapter
from food_procurement_intelligence.optimization.scenario_adapter import SavedPlanningScenarios, bundle_from_records
from food_procurement_intelligence.simulation.contracts import SimulationSettings, Supplier


def save_gzip(path: Path, value) -> None:
    with path.open('xb') as file:
        with gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0) as stream:
            stream.write(json.dumps(_serializable(value),sort_keys=True,ensure_ascii=False,allow_nan=False).encode())


def read_gzip(path: Path):
    with gzip.open(path,'rt',encoding='utf-8') as file: return json.load(file)


def prepare_resources(root: Path, cache: Path | None = None) -> dict:
    _,d9,plan,d8,d7,d6=load_day9(root/'configs/day9.toml')
    origins=months_between(plan.validation_origin_start,plan.validation_origin_end)
    models={'sarimax':d8['models'][0],'lightgbm':d8['models'][1]}
    if cache is None:
        points={label:load_point_adapter(root/d7[label+'_run'],plan,model) for label,model in models.items()}
        scenario=SavedPlanningScenarios(root/d8['day6_run'],root,plan,d8['day6_manifest_sha256'])
        inputs=PreparedPolicyInputs(origins,models,points,scenario)
    else:
        data=read_gzip(cache)
        pmap,bmap={},{}
        for row in data:
            origin=parse_month_label(row['origin']);label=row['label'];model=models[label]
            pmap[(label,origin)]=tuple(ModelPrediction(origin,parse_month_label(p['information_cutoff']),
                parse_month_label(p['target_month']),p['horizon'],p['predicted_price'],p['model_name'],p['unit']) for p in row['points'])
            bmap[(model,origin)]=bundle_from_records(row['scenarios'],origin,model)
        inputs=PreparedPolicyInputs(origins,models,{label:(lambda o,label=label:pmap[(label,o)]) for label in models},lambda o,m:bmap[(m,o)])
    settings=SimulationSettings(**{k:d6['simulation'][k] for k in SimulationSettings.__dataclass_fields__})
    suppliers=tuple(Supplier(**r) for r in d6['suppliers'])
    store=load_development_store(root,root/'configs/day2.toml')
    reader=GuardedValidationPrices(store.validation_actuals_reader(),plan)
    prices=reader.frozen_path()
    world=HistoricalEvaluationWorld(d9['operations']['world_id'],plan.validation_target_start,plan.validation_target_end,
        prices,tuple((p.month,100.) for p in prices))
    return {'plan':plan,'d9':d9,'d8':d8,'d7':d7,'inputs':inputs,'settings':settings,'suppliers':suppliers,
            'store':store,'world':world,'reader_requests':reader.requests,'origins':origins,'models':models}


def input_records(resources: dict) -> list[dict]:
    inputs=resources['inputs']
    return [{'label':label,'origin':o.strftime('%Y-%m'),'points':[p.record() for p in inputs.point(label,o)],
             'scenarios':inputs.scenario(label,o).records()} for o in resources['origins'] for label in resources['models']]


SETTING_AXES={'initial_inventory':'initial_inventory_tonnes','unmet_penalty':'unmet_usd_per_tonne',
              'terminal_weight':'terminal_usd_per_tonne_deviation','holding_cost':'holding_usd_per_tonne_month'}


def cell_overrides(cell: dict, settings, suppliers, world):
    """Explicit OAT replacement; no policy or planning belief reads stress realizations."""
    axis,value=cell['axis'],cell.get('value')
    if axis in SETTING_AXES:
        settings=replace(settings,**{SETTING_AXES[axis]:value})
    elif axis=='supplier_b_capacity':
        suppliers=tuple(replace(s,monthly_capacity_tonnes=value) if s.supplier_id=='B' else s for s in suppliers)
    elif axis=='demand_stress':
        world=replace(world,realized_demands=tuple((m,value if '2022-01'<=m.strftime('%Y-%m')<='2022-03' else d) for m,d in world.realized_demands))
    elif axis=='delay_stress':
        world=replace(world,delays=tuple(('A',parse_month_label(m),int(value)) for m in ('2022-01','2022-02','2022-03')))
    elif axis!='baseline':
        raise ValueError('Unsupported cell axis: '+axis)
    if axis!='baseline': world=replace(world,scenario_id='day10|'+cell['id'])
    return settings,suppliers,world


def failure_status(result: dict, policy) -> str:
    if result['complete']: return 'COMPLETE'
    error=result['failure']
    if error['error_type'] in ('LeakageError','HoldoutLockedError','LookupError','InputPreparationError'):
        return 'FAILED_AVAILABILITY'
    solutions=getattr(policy,'solutions',[])
    if solutions and not solutions[-1].accepted:
        if solutions[-1].status!='OPTIMAL': return 'FAILED_SOLVER'
        return 'FAILED_PHYSICAL_VALIDATION'
    if 'capacity' in error['error'].lower() or 'quantity' in error['error'].lower(): return 'UNSUPPORTED_CONTRACT'
    return 'INCOMPLETE_EVALUATION'


def rank_policies(full_metrics: list[dict], complete: bool, tolerance: float = 1e-4) -> list[dict]:
    if not complete: return []
    ranked=[]
    for row in full_metrics:
        lower=sum(r['total_cost']<row['total_cost']-tolerance for r in full_metrics)
        dominated=any(r['total_cost']<=row['total_cost']+tolerance and r['fill_rate']>=row['fill_rate']-1e-12
            and (r['total_cost']<row['total_cost']-tolerance or r['fill_rate']>row['fill_rate']+1e-12) for r in full_metrics)
        ranked.append({'policy':row['policy'],'rank':1+lower,'total_cost':row['total_cost'],'fill_rate':row['fill_rate'],
                       'cost_service_dominated':dominated})
    return ranked


def run_cell(cell: dict, resources: dict, directory: Path) -> dict:
    directory.mkdir(parents=True,exist_ok=False)
    settings,suppliers,world=cell_overrides(cell,resources['settings'],resources['suppliers'],resources['world'])
    plan=resources['plan'];results={};metrics=[];timings=[];statuses=[];runoff=[]
    save_json(directory/'inputs.json',_serializable({'cell':cell,'settings':asdict(settings),'suppliers':[asdict(s) for s in suppliers],
        'world':{'id':world.scenario_id,'start':world.start,'end':world.end,'price_sha256':record_hash([asdict(p) for p in world.prices]),
                 'demands':world.realized_demands,'delays':world.delays},'initial_pipeline':[]}))
    for name in POLICIES:
        policy=make_policy(name,resources['inputs'],settings,resources['d7']['lp'],resources['d8']['risk'],plan.validation_origin_end)
        result=run_historical_policy(world,settings,suppliers,policy,plan.validation_origin_start,plan.validation_origin_end,resources['store'].history_as_of)
        results[name]=result
        status=failure_status(result,policy)
        statuses.append({'policy':name,'status':status,'failure':result['failure'],'decision_count':len(result['decision_audit']),
                         'ledger_months':len(result['ledger']),'fallback':None,
                         'solver_failure_count':sum(not s.accepted for s in getattr(policy,'solutions',[])),
                         'asof_failure_count':int(status=='FAILED_AVAILABILITY'),
                         'maximum_quantity_violation':max((s.diagnostics.get('max_quantity_violation',0) or 0 for s in getattr(policy,'solutions',[])),default=0),
                         'numerical_validation_passed':all(s.accepted for s in getattr(policy,'solutions',[]))})
        for kind in ('ledger','orders','receipts'):
            save_csv(directory/(name+'_'+kind+'.csv'),_serializable(result[kind]))
        audits=[]
        for r in result['decision_audit']:
            context=r['context'];history=context['published_prices']
            audits.append({**r,'context':{**context,'published_prices':[],
                'public_history_count':len(history),'public_history_sha256':record_hash(history),
                'latest_public_month':max((p['month'] for p in history),default=None),
                'maximum_publication_at':max((p['available_at'] for p in history),default=None)}})
        save_json(directory/(name+'_decision_audit.json'),_serializable(audits))
        packed=[]
        for i,(history,solution) in enumerate(zip(getattr(policy,'history',[]),getattr(policy,'solutions',[]))):
            row=dict(history)
            scenario_rows=row.pop('planning_scenarios',None)
            if scenario_rows is not None: row['planning_sha256']=record_hash(scenario_rows)
            row['lp_text']=solution.lp_text
            packed.append(row)
            timings.append({'cell':cell['id'],'policy':name,'origin':resources['origins'][i].strftime('%Y-%m'),
                'status':solution.status,'seconds':solution.solve_seconds})
        save_gzip(directory/(name+'_plans.json.gz'),packed)
        if result['complete']:
            for period in ('full','active','runoff'):
                row=period_metrics(result,period,suppliers)
                metrics.append({'cell':cell['id'],'policy':name,**row,
                    'orders_by_supplier':{s.supplier_id:math.fsum(o['quantity_tonnes'] for o in result['orders'] if o['supplier_id']==s.supplier_id) for s in suppliers},
                    'ending_pipeline':result['summary']['terminal_outstanding_tonnes'],
                    'optimal_count':sum(s.status=='OPTIMAL' for s in getattr(policy,'solutions',[])),
                    'asof_failure_count':0,'missing_input_count':0,'fallback_count':0,'status':'COMPLETE'})
            active=result['ledger'][34]
            runoff.append({'cell':cell['id'],'policy':name,'last_active_inventory':active['ending_inventory'],
                'last_active_pipeline':active['outstanding_orders'],
                'runoff_months':[{k:r[k] for k in ('month','received_quantity','fulfilled_demand','unmet_demand','ending_inventory','new_order_quantity','total_cost','terminal_cost','outstanding_quantity')}
                                 for r in result['ledger'] if r['period']=='runoff'],
                'final_inventory':result['ledger'][-1]['ending_inventory'],'final_pipeline':result['ledger'][-1]['outstanding_quantity']})
    complete=all(r['complete'] for r in results.values())
    full=[r for r in metrics if r['period']=='full']
    ranks=rank_policies(full,complete)
    save_json(directory/'statuses.json',_serializable(statuses));save_json(directory/'metrics.json',metrics)
    save_json(directory/'runoff_audit.json',_serializable(runoff));save_json(directory/'ranks.json',ranks)
    if complete:
        extra=tuple((p+'_minus_fixed',p,'fixed') for p in POLICIES if p!='fixed' and (p+'_minus_fixed',p,'fixed') not in PAIRS)
        monthly,paired=paired_comparison(results,PAIRS+extra)
        save_csv(directory/'paired_monthly.csv',_serializable(monthly));save_json(directory/'paired_summary.json',paired)
    else:
        paired=[]
        save_json(directory/'comparison_unavailable.json',{'reason':'At least one policy incomplete; no seven-policy ranks or full comparison',
            'successful_policies':[r['policy'] for r in statuses if r['status']=='COMPLETE']})
    return {'id':cell['id'],'status':'COMPLETE' if complete else 'INCOMPLETE_EVALUATION','statuses':statuses,
            'metrics':metrics,'ranks':ranks,'paired':paired,'timings':timings}


def baseline_gate(directory: Path, reference: Path) -> dict:
    checked=[]
    for name in POLICIES:
        for kind in ('orders','receipts','ledger'):
            file=name+'_'+kind+'.csv'
            if digest(directory/file)!=digest(reference/file): raise ArithmeticError('Baseline regression mismatch: '+file)
            checked.append(file)
    new=json.loads((directory/'metrics.json').read_text())
    old=json.loads((reference/'policy_metrics.json').read_text())
    for row in new:
        target=next(r for r in old if r['policy']==row['policy'] and r['period']==row['period'])
        for key in (*COST_KEYS,'realized_demand','fulfilled_demand','unmet_demand','fill_rate','stockout_months','average_inventory','ending_inventory'):
            if row[key]!=target[key]: raise ArithmeticError('Baseline metric mismatch: '+key)
    return {'passed':True,'exact_flow_files':len(checked),'period_metric_rows':len(new),'checked_files':checked,
            'reference_manifest_sha256':digest(reference/'manifest.json')}


def validate_grid(config: dict) -> None:
    expected={'initial_inventory':{100.,300.},'unmet_penalty':{750.,3000.},'terminal_weight':{0.,30.},
              'holding_cost':{6.},'supplier_b_capacity':{60.}}
    cells=config['cells']
    if len(cells)!=14 or len({c['id'] for c in cells})!=14: raise ValueError('Frozen grid must retain all 14 unique cells')
    actual={axis:{c['value'] for c in cells if c['kind']=='oat' and c['axis']==axis} for axis in expected}
    if actual!=expected or sum(c['kind']=='oat' for c in cells)!=8: raise ValueError('OAT specification changed')
    if [c['axis'] for c in cells if c['kind']=='baseline']!=['baseline']: raise ValueError('One baseline required')
    if {(c['axis'],c['value']) for c in cells if c['kind']=='stress'}!={('demand_stress',120.),('delay_stress',1.)}:
        raise ValueError('Stress specification changed')
    if sum(c['kind']=='unsupported' and bool(c.get('reason')) for c in cells)!=3: raise ValueError('Keep unsupported reasons')
    if tuple(config['policies'])!=POLICIES or config['alpha']!=.9 or config['rn_lambda']!=0 or config['ra_lambda']!=.5:
        raise ValueError('Do not tune model/policy/risk specifications')


def stability_analysis(cells: list[dict], tolerance: float = 1e-4, near_tie: float = .001) -> dict:
    base=next(c for c in cells if c['id']=='baseline')
    baseline={r['policy']:r for r in base['ranks']}
    report=[];reversals=[]
    sign=lambda x:0 if abs(x)<=tolerance else 1 if x>0 else -1
    for cell in cells:
        if cell['status']!='COMPLETE':
            report.append({'id':cell['id'],'status':cell['status'],'winners':None,'rank_changes':None})
            continue
        ranks={r['policy']:r for r in cell['ranks']}
        fixed=ranks['fixed']['total_cost'];delta=ranks['ra_sarimax']['total_cost']-fixed
        report.append({'id':cell['id'],'status':cell['status'],'winners':[p for p,r in ranks.items() if r['rank']==1],
            'rank_changes':{p:r['rank']-baseline[p]['rank'] for p,r in ranks.items()},
            'ra_sarimax_minus_fixed':delta,'near_tie_ra_sarimax_fixed':abs(delta/fixed)<=near_tie if fixed else None})
        for i,a in enumerate(POLICIES):
            for b in POLICIES[i+1:]:
                before=sign(baseline[a]['total_cost']-baseline[b]['total_cost'])
                after=sign(ranks[a]['total_cost']-ranks[b]['total_cost'])
                if before!=after:
                    reversals.append({'cell':cell['id'],'left':a,'right':b,'baseline_relation':before,
                        'cell_relation':after,'strict_reversal':before*after<0})
    return {'cells':report,'pair_order_changes':reversals,'rank_is_cost_only':True,'cells_are_probability_samples':False}
