"""Independent all-cell physical/cost/LP/stability checks; no policy/solver calls."""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

from verify_day8_results import close,index,label,paths_from_rows,verify_plan

ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def compressed(p):
    with gzip.open(p,'rt',encoding='utf-8') as f:return json.load(f)
def rows(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))


def check_cell(directory,report,shared,origin_audit):
    inputs=read(directory/'inputs.json');settings=inputs['settings'];suppliers={s['supplier_id']:s for s in inputs['suppliers']}
    demands=dict(inputs['world']['demands']);delays={(s,m):v for s,m,v in inputs['world']['delays']}
    source=read(ROOT/'artifacts/day9/20261030T090528446877Z/manifest.json')['source_data']
    prices={r['date'][:7]:float(r['price']) for r in rows(ROOT/source['path']) if '2021-07'<=r['date'][:7]<='2024-08'}
    checked={};solves=0
    for status in report['statuses']:
        name=status['policy'];ledger=rows(directory/(name+'_ledger.csv'));orders=rows(directory/(name+'_orders.csv'));receipts=rows(directory/(name+'_receipts.csv'))
        if status['status']!='COMPLETE':
            assert report['ranks']==[] and not ledger and status['failure'] is not None
            continue
        assert len(ledger)==38 and len(orders)==len(receipts)==len({o['order_id'] for o in orders})
        cohorts={}
        for o in orders:
            s=suppliers[o['supplier_id']];k=o['order_month'];q=float(o['quantity_tonnes'])
            assert '2021-06'<=k<='2024-05' and q>0 and index(k)+s['lead_time_months']+s['maximum_delay_months']<=index('2024-08')
            key=o['supplier_id'],k;cohorts[key]=cohorts.get(key,0.)+q
            assert cohorts[key]<=s['monthly_capacity_tonnes']+1e-7
            arrival=label(index(k)+s['lead_time_months']+delays.get(key,0))
            receipt=next(r for r in receipts if r['order_id']==o['order_id'])
            assert receipt['receipt_month']==arrival
            close(float(receipt['procurement_cost']),q*prices[arrival]*(1+s['price_premium']))
        inventory=settings['initial_inventory_tonnes']
        for r in ledger:
            m=r['month'];incoming=[x for x in receipts if x['receipt_month']==m]
            available=inventory+sum(float(x['quantity_tonnes']) for x in incoming)
            served=min(available,demands[m]);unmet=demands[m]-served
            waste=max(available-served-settings['warehouse_capacity_tonnes'],0.)
            close(float(r['beginning_inventory']),inventory,1e-7);inventory=available-served-waste
            for k,v in (('fulfilled_demand',served),('unmet_demand',unmet),('disposed_quantity',waste),('ending_inventory',inventory),('realized_demand',demands[m])):
                close(float(r[k]),v,1e-7)
            costs={'procurement_cost':sum(float(x['procurement_cost']) for x in incoming),
                'transport_cost':sum(float(x['transport_cost']) for x in incoming),
                'holding_cost':inventory*settings['holding_usd_per_tonne_month'],'unmet_cost':unmet*settings['unmet_usd_per_tonne'],
                'disposal_cost':waste*settings['disposal_usd_per_tonne'],
                'terminal_cost':abs(inventory-settings['terminal_target_tonnes'])*settings['terminal_usd_per_tonne_deviation'] if m=='2024-08' else 0.}
            costs['total_cost']=sum(costs.values())
            for k,v in costs.items():close(float(r[k]),v)
            if m>'2024-05':close(float(r['new_order_quantity']),0.,1e-7)
        close(float(ledger[-1]['outstanding_quantity']),0.,1e-7)
        decisions=read(directory/(name+'_decision_audit.json'));plans=compressed(directory/(name+'_plans.json.gz'))
        assert len(decisions)==36 and decisions[0]['context']['outstanding_orders']==[]
        close(decisions[0]['context']['on_hand_tonnes'],settings['initial_inventory_tonnes'])
        for d in decisions:
            ctx=d['context'];o=d['origin']
            assert index(ctx['latest_public_month'])==index(o)-1
            assert ctx['planned_demand_tonnes']==100. and ctx['suppliers']==inputs['suppliers']
            actual=[x for x in orders if x['order_month']==o]
            close(sum(float(x['quantity_tonnes']) for x in actual),sum(x['quantity_tonnes'] for x in d['orders']))
        if name=='fixed':assert plans==[]
        else:
            assert len(plans)==36
            model=name.split('_',1)[1]
            for p,d in zip(plans,decisions):
                result=p['plan'];diag=result['diagnostics'];o=p['origin'];inputs_key=(model,o)
                assert result['accepted'] and result['status']=='OPTIMAL' and diag['calendar_passed']
                assert diag['ortools_verify_solution'] and not diag['violations']
                for sid in suppliers:
                    raw=result['variables']['q'][sid+'|'+o]
                    close(raw,sum(x['quantity_tonnes'] for x in d['orders'] if x['supplier_id']==sid),1e-7)
                assert all(abs(v)<=1e-7 for v in diag['calendar_future_q'].values())
                source_input=shared[inputs_key]
                if name.startswith(('rn_','ra_')):
                    assert p['planning_sha256']==origin_audit[inputs_key]['planning_sha256']
                    verify_plan(result,d['context'],settings,paths_from_rows(source_input['scenarios']),result['provenance']['risk'])
                else:
                    assert p['forecasts']==source_input['points']
                    path={x['target_month']:x['predicted_price'] for x in p['forecasts']}
                    synthetic={**result,'expected_cost':result['objective'],'var':result['objective'],'cvar':result['objective'],
                        'scenario_costs':[{'scenario_id':'point','probability':1.,'components':result['components'],'total_cost':result['objective']}]}
                    verify_plan(synthetic,d['context'],settings,[('point',1.,path)],{'alpha':.9,'risk_weight':0.},False)
                solves+=1
        for metric in [r for r in report['metrics'] if r['policy']==name]:
            selected=[r for r in ledger if metric['period']=='full' or r['period']==metric['period']]
            for k in ('procurement_cost','transport_cost','holding_cost','unmet_cost','disposal_cost','terminal_cost','total_cost','realized_demand','fulfilled_demand','unmet_demand'):
                close(metric[k],sum(float(r[k]) for r in selected))
            close(metric['fill_rate'],metric['fulfilled_demand']/metric['realized_demand'])
            close(metric['average_inventory'],sum(float(r['ending_inventory']) for r in selected)/len(selected))
            for sid,v in metric['orders_by_supplier'].items():close(v,sum(float(o['quantity_tonnes']) for o in orders if o['supplier_id']==sid))
        checked[name]=ledger
    if report['status']=='COMPLETE':
        full=[m for m in report['metrics'] if m['period']=='full'];assert len(full)==7 and solves==216
        for rank in report['ranks']:
            metric=next(m for m in full if m['policy']==rank['policy'])
            assert rank['rank']==1+sum(m['total_cost']<metric['total_cost']-1e-4 for m in full)
        for pair in rows(directory/'paired_monthly.csv'):
            a=next(x for x in checked[pair['left']] if x['month']==pair['month']);b=next(x for x in checked[pair['right']] if x['month']==pair['month'])
            for k in pair:
                if k=='fill_rate_difference':close(float(pair[k]),float(a['fulfilled_demand'])/float(a['realized_demand'])-float(b['fulfilled_demand'])/float(b['realized_demand']))
                elif k.endswith('_difference'):close(float(pair[k]),float(a[k[:-11]])-float(b[k[:-11]]))
        for ra in read(directory/'runoff_audit.json'):
            ledger=checked[ra['policy']]
            close(ra['last_active_inventory'],float(ledger[34]['ending_inventory']))
            assert ra['last_active_pipeline']==json.loads(ledger[34]['outstanding_orders'])
            for actual,stored in zip(ledger[35:],ra['runoff_months']):
                for k in ('received_quantity','fulfilled_demand','unmet_demand','ending_inventory','new_order_quantity','total_cost','terminal_cost','outstanding_quantity'):close(float(actual[k]),stored[k])
    return solves


def verify(directory: Path,repeat: Path | None = None):
    manifest=read(directory/'manifest.json');assert manifest['holdout_locked'] and manifest['baseline_gate_passed']
    for group in ('output_sha256','code_sha256','source_links'):
        for name,value in manifest[group].items():assert sha(ROOT/name)==value,name
    assert sha(ROOT/'configs/day10.toml')==manifest['config_sha256'] and sha(ROOT/'docs/DAY10_SENSITIVITY_PROTOCOL.md')==manifest['protocol_sha256']
    old=read(ROOT/'artifacts/day10/preservation_before.json')
    for name,value in old['sha256'].items():assert sha(ROOT/name)==value,name
    for name,info in old['append_only'].items():assert hashlib.sha256((ROOT/name).read_bytes()[:info['bytes']]).hexdigest()==info['sha256']
    cache=ROOT/manifest['planning_cache_path'];assert sha(cache)==manifest['planning_cache_sha256']
    shared={(r['label'],r['origin']):r for r in compressed(cache)}
    common=read(directory/'common_provenance.json');audit={(r['label'],r['origin']):r for r in common['input_audit']}
    assert len(common['evaluation_unique_months'])==len(set(common['evaluation_unique_months']))==38
    reports=read(directory/'cell_results.json');assert len(reports)==14
    solves=0
    for report in reports:
        if report['status']=='UNSUPPORTED_CONTRACT' and 'statuses' not in report:
            assert report['reason'] and not report['metrics'] and not report['ranks'];continue
        solves+=check_cell(directory/report['id'],report,shared,audit)
    reference=ROOT/manifest['config']['day9_reference']
    for name in manifest['config']['policies']:
        for kind in ('orders','receipts','ledger'):assert sha(directory/'baseline'/(name+'_'+kind+'.csv'))==sha(reference/(name+'_'+kind+'.csv'))
    stability=read(directory/'stability.json');baseline=next(r for r in reports if r['id']=='baseline')
    baseline_cost={r['policy']:r['total_cost'] for r in baseline['ranks']}
    for r in stability['pair_order_changes']:
        cell=next(x for x in reports if x['id']==r['cell']);cost={x['policy']:x['total_cost'] for x in cell['ranks']}
        assert r['strict_reversal']==((baseline_cost[r['left']]-baseline_cost[r['right']])*(cost[r['left']]-cost[r['right']])<0)
    for r in rows(directory/'risk_increment.csv'):
        cell=next(x for x in reports if x['id']==r['cell']);model=r['model']
        rn=next(x for x in cell['metrics'] if x['policy']=='rn_'+model and x['period']=='full')
        ra=next(x for x in cell['metrics'] if x['policy']=='ra_'+model and x['period']=='full')
        for key,a,b in (('ra_minus_rn_cost',ra['total_cost'],rn['total_cost']),('inventory_difference',ra['average_inventory'],rn['average_inventory']),('fill_rate_difference',ra['fill_rate'],rn['fill_rate'])):close(float(r[key]),a-b)
    n=0
    if repeat:
        other=read(repeat/'manifest.json');assert manifest['config_sha256']==other['config_sha256'] and manifest['code_sha256']==other['code_sha256']
        for parent,peer in ((directory,repeat),(ROOT/manifest['synthetic_directory'],ROOT/other['synthetic_directory'])):
            for file in parent.rglob('*'):
                if file.is_file() and file.name not in ('manifest.json','spec_freeze.json','solver_timing.json'):
                    assert sha(file)==sha(peer/file.relative_to(parent)),str(file);n+=1
    return {'passed':True,'protected_files':len(old['sha256']),'append_only_documents':3,'total_cells':len(reports),
        'complete_cells':sum(r['status']=='COMPLETE' for r in reports),'unsupported_cells':sum(r['status']=='UNSUPPORTED_CONTRACT' for r in reports),
        'independently_checked_optimal_plans':solves,'deterministic_files_equal':n}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--repeat',type=Path)
    a=p.parse_args();result=verify(a.run,a.repeat)
    with (ROOT/'artifacts/day10'/('verification_'+a.run.name+('_repeat' if a.repeat else '')+'.json')).open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
