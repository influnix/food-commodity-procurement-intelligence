"""Frozen OAT/stress diagnostic; baseline regression is mandatory on every run."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import sys
import tomllib

from food_procurement_intelligence.evaluation.model_backtesting import digest,save_json,save_csv
from food_procurement_intelligence.evaluation.sensitivity import (
    prepare_resources,run_cell,baseline_gate,validate_grid,stability_analysis,
)


def preserve(root: Path) -> int:
    snapshot=json.loads((root/'artifacts/day10/preservation_before.json').read_text(encoding='utf-8'))
    for name,sha in snapshot['sha256'].items():
        if digest(root/name)!=sha: raise ValueError('Old file changed: '+name)
    for name,info in snapshot['append_only'].items():
        if hashlib.sha256((root/name).read_bytes()[:info['bytes']]).hexdigest()!=info['sha256']:
            raise ValueError('Old document prefix changed: '+name)
    return len(snapshot['sha256'])


def load_day10(path: Path):
    root=path.resolve().parent.parent
    config=tomllib.loads(path.read_text(encoding='utf-8'))
    validate_grid(config)
    if config['holdout_locked'] is not True: raise ValueError('Holdout remains locked')
    freeze=json.loads((root/'artifacts/day10/protocol_freeze.json').read_text(encoding='utf-8'))
    if digest(path)!=freeze['config_sha256'] or digest(root/'docs/DAY10_SENSITIVITY_PROTOCOL.md')!=freeze['protocol_sha256']:
        raise ValueError('Cell-result specification changed after freeze')
    regression=json.loads((root/'artifacts/day10/baseline_regression.json').read_text(encoding='utf-8'))
    if not regression['passed'] or regression['exact_flow_files']!=21: raise ValueError('Baseline gate failed')
    cache=root/regression['directory']/'shared_inputs.json.gz'
    if digest(cache)!=regression['shared_inputs_sha256']: raise ValueError('Immutable planning input cache changed')
    gate=json.loads((root/'artifacts/day10/toy_gate.json').read_text(encoding='utf-8'))
    if gate['exit_code']!=0: raise ValueError('Toy checks must pass first')
    for name,expected in gate['sha256'].items():
        if digest(root/name)!=expected: raise ValueError('Toy-verified code changed')
    preserve(root)
    return root,config,cache


def run_day10(path: Path) -> dict:
    root,config,cache=load_day10(path)
    identifier=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=root/config['report_root']/('run_'+identifier)
    directory.mkdir(parents=True,exist_ok=False)
    synthetic=root/config['synthetic_root']/('run_'+identifier)
    synthetic.mkdir(parents=True,exist_ok=False)
    save_json(directory/'spec_freeze.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'config':config,
        'config_sha256':digest(path),'protocol_sha256':digest(root/'docs/DAY10_SENSITIVITY_PROTOCOL.md'),'cell_results_started':False})
    resources=prepare_resources(root,cache)
    save_json(directory/'common_provenance.json',{'planning_cache_sha256':digest(cache),
        'baseline_regression_sha256':digest(root/'artifacts/day10/baseline_regression.json'),
        'input_audit':[{**r,'origin':r['origin'].strftime('%Y-%m')} for r in resources['inputs'].audit],
        'evaluation_unique_months':resources['reader_requests'],'new_training_or_forecasts':False,'bridge_or_holdout_used':False})
    reports=[];metrics=[];timings=[];increments=[]
    for cell in config['cells']:
        if cell['kind']=='unsupported':
            reports.append({'id':cell['id'],'status':'UNSUPPORTED_CONTRACT','reason':cell['reason'],'metrics':[],'ranks':[]})
            continue
        report=run_cell(cell,resources,directory/cell['id'])
        save_json(synthetic/(cell['id']+'.json'),{'generator':'explicit_cell_replace_v1','rng':'none',
            'quantity_unit':'metric_tonne','cost_unit':'USD','config_sha256':digest(path),
            'inputs':json.loads((directory/cell['id']/'inputs.json').read_text(encoding='utf-8'))})
        if cell['id']=='baseline':
            gate=baseline_gate(directory/'baseline',root/config['day9_reference'])
            save_json(directory/'baseline_regression.json',gate)
        reports.append(report);metrics.extend(report['metrics']);timings.extend(report.pop('timings'))
        if report['status']=='COMPLETE':
            for model in ('sarimax','lightgbm'):
                rn=next(r for r in report['metrics'] if r['policy']=='rn_'+model and r['period']=='full')
                ra=next(r for r in report['metrics'] if r['policy']=='ra_'+model and r['period']=='full')
                increments.append({'cell':cell['id'],'model':model,'ra_minus_rn_cost':ra['total_cost']-rn['total_cost'],
                    'inventory_difference':ra['average_inventory']-rn['average_inventory'],'fill_rate_difference':ra['fill_rate']-rn['fill_rate'],
                    'a_order_difference':ra['orders_by_supplier']['A']-rn['orders_by_supplier']['A'],
                    'b_order_difference':ra['orders_by_supplier']['B']-rn['orders_by_supplier']['B'],
                    **{p+'_cost_difference':next(r['cost_difference'] for r in report['paired'] if r['comparison']=='ra_'+model+'_minus_rn' and r['period']==p) for p in ('active','runoff')}})
        print(json.dumps({'cell':cell['id'],'status':report['status']},ensure_ascii=False),flush=True)
    stability=stability_analysis(reports,config['cost_tie_tolerance_usd'],config['near_tie_fraction'])
    save_json(directory/'cell_results.json',reports)
    save_json(directory/'policy_metrics.json',metrics)
    save_csv(directory/'policy_matrix.csv',[r for r in metrics if r['period']=='full'])
    save_json(directory/'stability.json',stability);save_csv(directory/'risk_increment.csv',increments)
    save_json(directory/'solver_timing.json',timings)
    save_json(directory/'failure_unsupported_report.json',[{'id':r['id'],'status':r['status'],'reason':r.get('reason'),
        'policy_statuses':r.get('statuses',[])} for r in reports])
    preserve(root)
    from ortools.linear_solver import _pywraplp
    sources=[Path(__file__),root/'src/food_procurement_intelligence/evaluation/sensitivity.py',root/'scripts/verify_day10_results.py']
    old=json.loads((root/config['day9_reference']/'manifest.json').read_text(encoding='utf-8'))
    save_json(directory/'manifest.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'config':config,
        'config_sha256':digest(path),'protocol_sha256':digest(root/'docs/DAY10_SENSITIVITY_PROTOCOL.md'),
        'day9_manifest_sha256':digest(root/config['day9_reference']/'manifest.json'),'source_links':old['source_links'],
        'source_data':old['source_data'],'raw_sha256':old['raw_sha256'],'python':sys.version,
        'versions':{name:version(name) for name in ('ortools','numpy','pandas','statsmodels','lightgbm','protobuf')},
        'solver_binary_sha256':digest(Path(_pywraplp.__file__)),'planning_cache_path':cache.relative_to(root).as_posix(),
        'synthetic_directory':synthetic.relative_to(root).as_posix(),
        'planning_cache_sha256':digest(cache),'code_sha256':{p.relative_to(root).as_posix():digest(p) for p in sources},
        'output_sha256':{p.relative_to(root).as_posix():digest(p) for parent in (directory,synthetic) for p in sorted(parent.rglob('*')) if p.is_file()},
        'holdout_locked':True,'baseline_gate_passed':True,'independent_oos_claim':False,'post_day9_diagnostic':True})
    return {'directory':directory.relative_to(root).as_posix(),'cells':[{k:r[k] for k in ('id','status')} for r in reports]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,default=Path('configs/day10.toml'))
    args=parser.parse_args();print(json.dumps(run_day10(args.config),indent=2))
