"""Independent historical receipts/inventory/cost/paired arithmetic, no solver."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.validation.verify_scenario_plans import close, index, label, paths_from_rows, verify_plan

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(path):
    with path.open(encoding='utf-8',newline='') as f: return list(csv.DictReader(f))


def verify_policy(directory,policy,operations,prices):
    settings=operations['settings']
    suppliers={s['supplier_id']:s for s in operations['suppliers']}
    ledger=rows(directory/(policy+'_ledger.csv'))
    orders=rows(directory/(policy+'_orders.csv'))
    receipts=rows(directory/(policy+'_receipts.csv'))
    decisions=read(directory/(policy+'_decision_audit.json'))
    plans=read(directory/(policy+'_rolling_plans.json'))
    assert len(ledger)==38 and len(decisions)==36
    assert [r['month'] for r in ledger]==[label(n) for n in range(index('2021-07'),index('2024-08')+1)]
    assert [r['origin'] for r in decisions]==[label(n) for n in range(index('2021-06'),index('2024-05')+1)]
    first=decisions[0]['context']
    assert first['outstanding_orders']==[] and first['on_hand_tonnes']==200.
    assert max(p['month'] for p in first['published_prices'])=='2021-05'
    assert read(directory/(policy+'_runoff.json'))==['2024-06','2024-07','2024-08']
    assert len(orders)==len({o['order_id'] for o in orders})==len(receipts)
    cohorts={}
    for o in orders:
        assert o['initial_pipeline']=='False'
        sid,k=o['supplier_id'],o['order_month']
        q=float(o['quantity_tonnes']); s=suppliers[sid]
        assert index('2021-06')<=index(k)<=index('2024-05') and q>0
        assert index(k)+s['lead_time_months']+s['maximum_delay_months']<=index('2024-08')
        cohorts[(sid,k)]=cohorts.get((sid,k),0.)+q
        assert cohorts[(sid,k)]<=s['monthly_capacity_tonnes']+1e-7
        r=next(r for r in receipts if r['order_id']==o['order_id'])
        assert r['receipt_month']==label(index(k)+s['lead_time_months'])
        close(float(r['quantity_tonnes']),q)
        close(float(r['market_price']),prices[r['receipt_month']])
        close(float(r['procurement_cost']),q*prices[r['receipt_month']]*(1+s['price_premium']))
    inventory=200.
    keys=('procurement_cost','transport_cost','holding_cost','unmet_cost','disposal_cost','terminal_cost','total_cost')
    for row in ledger:
        m=row['month']; incoming=[r for r in receipts if r['receipt_month']==m]
        received=sum(float(r['quantity_tonnes']) for r in incoming)
        close(float(row['beginning_inventory']),inventory,1e-7)
        available=inventory+received; served=min(available,100.); unmet=100.-served
        waste=max(available-served-400.,0.); inventory=available-served-waste
        for key,value in (('received_quantity',received),('fulfilled_demand',served),('unmet_demand',unmet),
                ('disposed_quantity',waste),('ending_inventory',inventory),('realized_demand',100.)):
            close(float(row[key]),value,1e-7)
        costs={'procurement_cost':sum(float(r['procurement_cost']) for r in incoming),
            'transport_cost':sum(float(r['transport_cost']) for r in incoming),'holding_cost':inventory*3.,
            'unmet_cost':unmet*1500.,'disposal_cost':waste,
            'terminal_cost':abs(inventory-200.)*9. if m=='2024-08' else 0.}
        costs['total_cost']=sum(costs.values())
        for key,value in costs.items(): close(float(row[key]),value)
        outstanding=sum(float(o['quantity_tonnes']) for o in orders if o['order_month']<=m and label(index(o['order_month'])+suppliers[o['supplier_id']]['lead_time_months'])>m)
        close(float(row['outstanding_quantity']),outstanding,1e-7)
        if m>'2024-05': close(float(row['new_order_quantity']),0.,1e-7)
        assert row['period']==('active' if m<='2024-05' else 'runoff')
    close(float(ledger[-1]['outstanding_quantity']),0.,1e-7)
    for decision in decisions:
        o=decision['origin']; context=decision['context']
        assert decision['completed']
        assert all(index(p['month'])<=index(o)-1 and p['available_at']<=o+'-31T23:59:59+00:00' for p in context['published_prices'])
        actual=[r for r in orders if r['order_month']==o]
        close(sum(float(r['quantity_tonnes']) for r in actual),sum(r['quantity_tonnes'] for r in decision['orders']))
        assert not any(k in context for k in ('prices','realized_demands','delays','reader','procurement_cost'))
    if policy=='fixed': assert plans==[]
    else:
        assert len(plans)==36
        for p,d in zip(plans,decisions):
            result=p['plan']; diag=result['diagnostics']
            assert result['status']=='OPTIMAL' and result['accepted'] and diag['calendar_passed'] and diag['ortools_verify_solution']
            assert all(abs(q)<=1e-7 for q in diag['calendar_future_q'].values())
            for sid in suppliers:
                current=result['variables']['q'][sid+'|'+p['origin']]
                executed=sum(r['quantity_tonnes'] for r in d['orders'] if r['supplier_id']==sid)
                close(current,executed,1e-7)
            if policy.startswith(('rn_','ra_')):
                verify_plan(result,d['context'],settings,paths_from_rows(p['planning_scenarios']),result['provenance']['risk'])
            else:
                path={r['target_month']:r['predicted_price'] for r in p['forecasts']}
                check={**result,'expected_cost':result['objective'],'var':result['objective'],'cvar':result['objective'],
                    'scenario_costs':[{'scenario_id':'point','probability':1.,'components':result['components'],'total_cost':result['objective']}]}
                verify_plan(check,d['context'],settings,[('point',1.,path)],{'alpha':.9,'risk_weight':0.},False)
    return ledger,orders,plans


def verify(directory,repeat=None):
    manifest=read(directory/'manifest.json')
    assert manifest['complete'] and manifest['holdout_locked'] and not manifest['bridge_used']
    for group in ('output_sha256','code_sha256','source_links'):
        for name,value in manifest[group].items(): assert sha(ROOT/name)==value,name
    assert sha(ROOT/'configs/evaluation/validation.toml')==manifest['config_sha256']
    assert sha(ROOT/'docs/VALIDATION_RESULTS.md')==manifest['protocol_sha256']
    preserved=read(ROOT/'artifacts/day9/preservation_before.json')
    for name,value in preserved['sha256'].items(): assert sha(ROOT/name)==value,name
    for name,info in preserved['append_only'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()[:info['bytes']]).hexdigest()==info['sha256']
    synthetic=ROOT/manifest['synthetic_directory']; operations=read(synthetic/'operations.json')
    assert operations['initial_pipeline']==[] and operations['settings']['initial_inventory_tonnes']==200.
    prices={r['observation_month']:float(r['price']) for r in rows(directory/'evaluation_prices.csv')}
    assert len(prices)==38
    audit=read(directory/'evaluation_reader_audit.json')
    assert audit['request_count']==len(set(audit['unique_requests']))==38 and not audit['bridge_holdout_requested']
    # Independent source comparison: filter dates before decoding numeric source prices.
    source=manifest['source_data']
    source_path=ROOT/source['path']
    assert sha(source_path)==source['sha256']
    original={r['date'][:7]:float(r['price']) for r in rows(source_path) if r['date'][:7] in prices}
    assert original==prices
    checked={p:verify_policy(directory,p,operations,prices) for p in manifest['config']['evaluation']['policies']}
    metrics=read(directory/'policy_metrics.json')
    for row in metrics:
        ledger,orders,_=checked[row['policy']]
        selected=[r for r in ledger if row['period']=='full' or r['period']==row['period']]
        for key in ('procurement_cost','transport_cost','holding_cost','unmet_cost','disposal_cost','terminal_cost','total_cost','realized_demand','fulfilled_demand','unmet_demand'):
            close(row[key],sum(float(r[key]) for r in selected))
        close(row['fill_rate'],row['fulfilled_demand']/row['realized_demand'])
        close(row['average_inventory'],sum(float(r['ending_inventory']) for r in selected)/len(selected))
        assert row['stockout_months']==sum(float(r['unmet_demand'])>1e-7 for r in selected)
        for sid,value in row['orders_by_supplier_all_decisions'].items(): close(value,sum(float(o['quantity_tonnes']) for o in orders if o['supplier_id']==sid))
        assert row['runoff_no_action']==3 and row['failure_count']==row['fallback_count']==0
    for model in ('sarimax','lightgbm'):
        rn=checked['rn_'+model][2];ra=checked['ra_'+model][2]
        assert [r['planning_scenarios'] for r in rn]==[r['planning_scenarios'] for r in ra]
        assert all(r['plan']['provenance']['risk']['risk_weight']==0 for r in rn)
        assert all(r['plan']['provenance']['risk']['risk_weight']==.5 for r in ra)
    monthly=rows(directory/'paired_monthly.csv')
    for row in monthly:
        a=next(r for r in checked[row['left']][0] if r['month']==row['month'])
        b=next(r for r in checked[row['right']][0] if r['month']==row['month'])
        for key in row:
            if key=='fill_rate_difference': close(float(row[key]),float(a['fulfilled_demand'])/float(a['realized_demand'])-float(b['fulfilled_demand'])/float(b['realized_demand']))
            elif key.endswith('_difference'): close(float(row[key]),float(a[key[:-11]])-float(b[key[:-11]]))
    for row in read(directory/'paired_summary.json'):
        selected=[r for r in monthly if r['comparison']==row['comparison'] and (row['period']=='full' or row['period']==r['period'])]
        close(row['cost_difference'],sum(float(r['total_cost_difference']) for r in selected))
        close(row['unmet_difference'],sum(float(r['unmet_demand_difference']) for r in selected))
        a=[r for r in checked[row['left']][0] if row['period']=='full' or r['period']==row['period']]
        b=[r for r in checked[row['right']][0] if row['period']=='full' or r['period']==row['period']]
        close(row['fill_rate_difference'],sum(float(r['fulfilled_demand']) for r in a)/sum(float(r['realized_demand']) for r in a)
            -sum(float(r['fulfilled_demand']) for r in b)/sum(float(r['realized_demand']) for r in b))
    for row in rows(directory/'paired_decision_orders.csv'):
        comparison=next(r for r in read(directory/'paired_summary.json') if r['comparison']==row['comparison'])
        for sid in ('A','B'):
            a,b=[sum(float(o['quantity_tonnes']) for o in checked[comparison[k]][1] if o['supplier_id']==sid and o['order_month']==row['origin']) for k in ('left','right')]
            close(float(row[sid+'_order_difference']),a-b)
    timings=read(directory/'solver_timing.json')
    assert len(timings)==216 and all(r['status']=='OPTIMAL' and r['solve_seconds']>=0 for r in timings)
    n=0
    if repeat:
        peer=read(repeat/'manifest.json')
        assert manifest['config_sha256']==peer['config_sha256'] and manifest['code_sha256']==peer['code_sha256']
        for parent,other in ((directory,repeat),(synthetic,ROOT/peer['synthetic_directory'])):
            for f in parent.iterdir():
                if f.is_file() and f.name not in ('manifest.json','spec_freeze.json','solver_timing.json'):
                    assert sha(f)==sha(other/f.name),f.name
                    n+=1
    return {'passed':True,'protected_files':len(preserved['sha256']),'append_only_documents':3,
        'policies':7,'decisions_per_policy':36,'ledger_months_per_policy':38,'unique_evaluation_prices':38,
        'optimal_solves':216,'paired_months':len(monthly),'deterministic_files_equal':n}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--repeat',type=Path)
    a=p.parse_args();result=verify(a.run,a.repeat)
    output=ROOT/'artifacts/day9'/('verification_'+a.run.name+('_repeat' if a.repeat else '')+'.json')
    with output.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
