"""Independent Day11 saved arithmetic; never opens a market-data file or calls a solver."""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from random import Random

from verify_day8_results import close,index,label,paths_from_rows,verify_plan
from food_procurement_intelligence.evaluation.release_gate import source_read_guard,verify_frozen_manifest

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def rows(path):
    with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def zipped(path):return json.loads(gzip.decompress(path.read_bytes()))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory: Path) -> dict:
    with source_read_guard(ROOT) as access:
        manifest=read(directory/'final_freeze_manifest.json')
        pinned=read(directory/'freeze_digest.json')['sha256']
        gate=verify_frozen_manifest(directory/'final_freeze_manifest.json',pinned,ROOT)
        assert gate['status']=='NOT_READY' and gate['holdout_locked']
        for name,expected in manifest['outputs'].items():assert digest(directory/name)==expected
        fixture=ROOT/manifest['synthetic_directory']
        for name,expected in manifest['synthetic_outputs'].items():assert digest(fixture/name)==expected
        observations=read(fixture/'observations.json');operations=read(fixture/'operations.json')
        prices={r['observation_month']:r['price'] for r in observations}
        publication={r['observation_month']:r['available_at'] for r in observations}
        assert all(r['knowledge_type']=='synthetic_preflight_not_world_bank' for r in observations)
        for i,r in enumerate(observations):close(r['price'],100+2*(i%12))
        calendar=read(directory/'calendar.json')
        origins=[label(n) for n in range(index('2024-09'),index('2026-06')+1)]
        months=[label(n) for n in range(index('2024-10'),index('2026-09')+1)]
        assert calendar['origins']==origins and calendar['ledger_months']==months
        assert calendar['active_months']==months[:21] and calendar['runoff_months']==months[21:]
        fits=read(directory/'fit_audit.json');pools=read(directory/'pool_audit.json');purposes=read(directory/'purpose_checks.json')
        assert len(fits)==len(pools)==len(purposes)==44
        for r in fits:
            t=index(r['origin'])
            assert index(r['feature_cutoff'])==index(r['history_end'])==t-1
            assert index(r['latest_training_origin'])==t-4 and index(r['last_training_target'])==t-1
            assert r['steps_from_latest_observation']==[2,3,4]
            assert r['targets']==[label(t+h) for h in (1,2,3)]
            assert r['max_training_available_at']<=r['origin']+'-31T23:59:59+00:00'
        for r in pools:
            t=index(r['origin']);vectors=r['vector_proofs']
            assert 24<=len(vectors)<=60 and r['joint_pool_count']==len(vectors)
            assert [v['source_origin'] for v in vectors]==sorted({v['source_origin'] for v in vectors})
            for v in vectors:
                past=index(v['source_origin'])
                assert past+3<=t-1 and index(v['fit_cutoff'])==past-1
                assert v['targets']==[label(past+h) for h in (1,2,3)]
                assert all(a<=r['origin']+'-31T23:59:59+00:00' for a in v['available_at'])
                for h,(target,ratio) in enumerate(zip(v['targets'],v['ratios']),1):
                    prediction=prices[label(past-1)]+(.25*h if 'lightgbm' in r['model'].lower() else 0)
                    close(ratio,prices[target]/prediction)
            for c in r['calibration'].values():assert 24<=c['count']<=60 and c['rank']==__import__('math').ceil((c['count']+1)*.8)
        assert all(r['evaluation_rejected'] and r['planning_seed']!=r['evaluation_seed'] and r['probability_sum']==1 for r in purposes)
        settings=operations['settings'];suppliers={s['supplier_id']:s for s in operations['suppliers']}
        count=0;all_plans={}
        for policy in manifest['contract']['policies']:
            ledger=rows(directory/(policy+'_ledger.csv'));orders=rows(directory/(policy+'_orders.csv'));receipts=rows(directory/(policy+'_receipts.csv'))
            decisions=read(directory/(policy+'_decision_audit.json'));plans=zipped(directory/(policy+'_plans.json.gz'));all_plans[policy]=plans
            assert [r['month'] for r in ledger]==months and [r['origin'] for r in decisions]==origins
            assert read(directory/(policy+'_runoff.json'))==months[21:]
            assert decisions[0]['context']['outstanding_orders']==[] and decisions[0]['context']['on_hand_tonnes']==200
            assert len(orders)==len(receipts)==len({r['order_id'] for r in orders})
            cohorts={}
            for o in orders:
                sid,k=o['supplier_id'],o['order_month'];s=suppliers[sid];q=float(o['quantity_tonnes'])
                assert k in origins and q>0 and o['initial_pipeline']=='False'
                key=sid,k;cohorts[key]=cohorts.get(key,0)+q;assert cohorts[key]<=s['monthly_capacity_tonnes']+1e-7
                receipt=next(r for r in receipts if r['order_id']==o['order_id'])
                arrival=label(index(k)+s['lead_time_months']);assert receipt['receipt_month']==arrival
                close(float(receipt['quantity_tonnes']),q);close(float(receipt['market_price']),prices[arrival])
                close(float(receipt['procurement_cost']),q*prices[arrival]*(1+s['price_premium']))
            inventory=200
            for row in ledger:
                m=row['month'];incoming=[r for r in receipts if r['receipt_month']==m]
                close(float(row['beginning_inventory']),inventory)
                received=sum(float(r['quantity_tonnes']) for r in incoming);available=inventory+received
                served=min(available,100);unmet=100-served;waste=max(available-served-400,0);inventory=available-served-waste
                for key,value in (('received_quantity',received),('fulfilled_demand',served),('unmet_demand',unmet),('disposed_quantity',waste),('ending_inventory',inventory)):
                    close(float(row[key]),value)
                costs={'procurement_cost':sum(float(r['procurement_cost']) for r in incoming),
                    'transport_cost':sum(float(r['transport_cost']) for r in incoming),'holding_cost':inventory*3,
                    'unmet_cost':unmet*1500,'disposal_cost':waste,'terminal_cost':abs(inventory-200)*9 if m==months[-1] else 0}
                costs['total_cost']=sum(costs.values())
                for key,value in costs.items():close(float(row[key]),value)
                outstanding=sum(float(o['quantity_tonnes']) for o in orders if o['order_month']<=m and label(index(o['order_month'])+suppliers[o['supplier_id']]['lead_time_months'])>m)
                close(float(row['outstanding_quantity']),outstanding)
                assert row['period']==('active' if m<='2026-06' else 'runoff')
                if m>'2026-06':close(float(row['new_order_quantity']),0)
            close(float(ledger[-1]['outstanding_quantity']),0)
            for d in decisions:
                ctx=d['context'];o=d['origin'];public=ctx['published_prices']
                assert d['completed'] and max(p['month'] for p in public)==label(index(o)-1)
                assert all(index(p['month'])<=index(o)-1 and p['available_at']<=o+'-31T23:59:59+00:00' for p in public)
                assert not any(k in ctx for k in ('reader','prices','realized_demands','delays'))
                if o=='2024-09':assert '2024-09' not in {p['month'] for p in public}
                if o=='2024-10':assert '2024-09' in {p['month'] for p in public}
                close(sum(float(r['quantity_tonnes']) for r in orders if r['order_month']==o),sum(r['quantity_tonnes'] for r in d['orders']))
            if policy=='fixed':assert plans==[];continue
            assert len(plans)==22
            for p,d in zip(plans,decisions):
                result=p['plan'];ctx=d['context'];o=p['origin']
                assert result['accepted'] and result['status']=='OPTIMAL' and result['diagnostics']['calendar_passed']
                assert result['diagnostics']['ortools_verify_solution'] and not result['diagnostics']['violations']
                assert all(abs(v)<1e-7 for v in result['diagnostics']['calendar_future_q'].values())
                for sid in suppliers:
                    close(result['variables']['q'][sid+'|'+o],sum(x['quantity_tonnes'] for x in d['orders'] if x['supplier_id']==sid))
                if policy.startswith(('rn_','ra_')):
                    scenario_rows=p['planning_scenarios'];paths=paths_from_rows(scenario_rows)
                    assert len(paths)==128
                    pool=next(r for r in pools if r['origin']==o and r['model']==scenario_rows[0]['source_model'])
                    # Derivation and draws are recomputed independently from the written specification.
                    model=pool['model'];base=manifest['contract']['rolling']['planning_seed']
                    payload=f'{base}|{o}|{model}|planning'.encode()
                    derived=int.from_bytes(hashlib.sha256(payload).digest()[:16],'big')
                    recorded=int(scenario_rows[0]['seed'])
                    assert recorded==derived
                    rng=Random(recorded)
                    grouped={}
                    for r in scenario_rows:grouped.setdefault(r['scenario_id'],[]).append(r)
                    for group in grouped.values():
                        vector=pool['vector_proofs'][rng.randrange(len(pool['vector_proofs']))]
                        for r,ratio in zip(sorted(group,key=lambda r:r['horizon']),vector['ratios']):
                            h=r['horizon'];point=prices[label(index(o)-1)]+(.25*h if 'lightgbm' in model.lower() else 0)
                            assert r['source_oof_origin']==vector['source_origin'];close(r['price'],point*ratio)
                    verify_plan(result,ctx,settings,paths,result['provenance']['risk'])
                else:
                    path={r['target_month']:r['predicted_price'] for r in p['forecasts']}
                    fake={**result,'expected_cost':result['objective'],'var':result['objective'],'cvar':result['objective'],
                        'scenario_costs':[{'scenario_id':'point','probability':1.,'components':result['components'],'total_cost':result['objective']}]}
                    verify_plan(fake,ctx,settings,[('point',1.,path)],{'alpha':.9,'risk_weight':0.},False)
                count+=1
        for model in ('sarimax','lightgbm'):
            assert [r['planning_scenarios'] for r in all_plans['rn_'+model]]==[r['planning_scenarios'] for r in all_plans['ra_'+model]]
        assert count==132 and access['actual_source_opens']==0 and not access['blocked_attempts']
        return {'passed':True,'policies':7,'ledger_rows':168,'decisions':154,'independently_checked_plans':count,
                'fit_audits':44,'pool_audits':44,'actual_source_opens':0,'freeze_verified':True,'gate':'NOT_READY'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=verify(args.directory.resolve());args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
