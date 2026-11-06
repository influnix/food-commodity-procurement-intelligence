"""Independent saved native-integration proofs and arithmetic. No forecast/policy/solver calls."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))

import argparse
import csv
from calendar import monthrange
from datetime import date,datetime
import gzip
import hashlib
import json
from pathlib import Path
from random import Random
import tomllib

from scripts.validation.verify_scenario_plans import close,index,label,paths_from_rows,verify_plan
from food_procurement_intelligence.data.sequential import integration_source_guard

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def zipped(p):return json.loads(gzip.decompress(p.read_bytes()))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def value_hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,default=str,allow_nan=False).encode()).hexdigest()
def endstamp(month):
    year,number=map(int,month.split("-"))
    return f"{month}-{monthrange(year,number)[1]:02d}T23:59:59+00:00"

def rows(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))


def verify_calendar(directory,fixture,prices,pool_lookup,label_name,counts):
    o_count,n,active,solves=counts;target=directory/label_name
    calendar=read(target/'calendar.json');first,last,end=(calendar[k] for k in ('first_origin','last_origin','last_ledger'))
    months=[label(i) for i in range(index(first)+1,index(end)+1)];origins=[label(i) for i in range(index(first),index(last)+1)]
    assert len(origins)==o_count and len(months)==n and calendar['active_months']==active
    operations=read(fixture/(label_name+'_operations.json'));settings=operations['settings'];suppliers={s['supplier_id']:s for s in operations['suppliers']}
    metrics=read(target/'metrics.json');plans_all={};checked=0;ledgers={}
    for policy in ('fixed','fa_sarimax','rn_sarimax','ra_sarimax','fa_lightgbm','rn_lightgbm','ra_lightgbm'):
        ledger=rows(target/(policy+'_ledger.csv'));orders=rows(target/(policy+'_orders.csv'));receipts=rows(target/(policy+'_receipts.csv'))
        decisions=read(target/(policy+'_decision_audit.json'));plans=zipped(target/(policy+'_plans.json.gz'));plans_all[policy]=plans;ledgers[policy]=ledger
        assert [r['month'] for r in ledger]==months and [r['origin'] for r in decisions]==origins
        assert read(target/(policy+'_runoff.json'))==months[-3:]
        assert decisions[0]['context']['on_hand_tonnes']==200 and decisions[0]['context']['outstanding_orders']==[]
        assert len(orders)==len(receipts)==len({o['order_id'] for o in orders})
        cohorts={}
        for o in orders:
            s=suppliers[o['supplier_id']];k=o['order_month'];q=float(o['quantity_tonnes']);assert k in origins and q>0 and o['initial_pipeline']=='False'
            cohort=o['supplier_id'],k;cohorts[cohort]=cohorts.get(cohort,0)+q;assert cohorts[cohort]<=s['monthly_capacity_tonnes']+1e-7
            assert index(k)+s['lead_time_months']+s['maximum_delay_months']<=index(end)
            r=next(r for r in receipts if r['order_id']==o['order_id']);arrival=label(index(k)+s['lead_time_months'])
            assert r['receipt_month']==arrival;close(float(r['quantity_tonnes']),q);close(float(r['market_price']),prices[arrival])
            close(float(r['procurement_cost']),q*prices[arrival]*(1+s['price_premium']))
        inventory=200
        for r in ledger:
            m=r['month'];incoming=[x for x in receipts if x['receipt_month']==m];received=sum(float(x['quantity_tonnes']) for x in incoming)
            close(float(r['beginning_inventory']),inventory);available=inventory+received;served=min(available,100);unmet=100-served;waste=max(available-served-400,0);inventory=available-served-waste
            for k,v in (('received_quantity',received),('fulfilled_demand',served),('unmet_demand',unmet),('disposed_quantity',waste),('ending_inventory',inventory)):close(float(r[k]),v)
            costs={'procurement_cost':sum(float(x['procurement_cost']) for x in incoming),'transport_cost':sum(float(x['transport_cost']) for x in incoming),
                'holding_cost':inventory*3,'unmet_cost':unmet*1500,'disposal_cost':waste,'terminal_cost':abs(inventory-200)*9 if m==end else 0}
            costs['total_cost']=sum(costs.values())
            for k,v in costs.items():close(float(r[k]),v)
            outstanding=sum(float(x['quantity_tonnes']) for x in orders if x['order_month']<=m and label(index(x['order_month'])+suppliers[x['supplier_id']]['lead_time_months'])>m)
            close(float(r['outstanding_quantity']),outstanding)
            assert r['period']==('active' if m<=last else 'runoff')
            if m>last:close(float(r['new_order_quantity']),0)
        close(float(ledger[-1]['outstanding_quantity']),0)
        for d in decisions:
            ctx=d['context'];o=d['origin'];assert d['completed']
            assert max(p['month'] for p in ctx['published_prices'])==label(index(o)-1)
            assert all(p['month']<o and p['available_at']<=endstamp(o) for p in ctx['published_prices'])
            assert not any(k in ctx for k in ('reader','prices','realized_demands','delays'))
            close(sum(float(x['quantity_tonnes']) for x in orders if x['order_month']==o),sum(x['quantity_tonnes'] for x in d['orders']))
        for metric in (r for r in metrics if r['policy']==policy):
            selected=[r for r in ledger if metric['period']=='full' or r['period']==metric['period']]
            for k in ('procurement_cost','transport_cost','holding_cost','unmet_cost','disposal_cost','terminal_cost','total_cost','realized_demand','fulfilled_demand','unmet_demand'):
                close(metric[k],sum(float(r[k]) for r in selected))
            close(metric['fill_rate'],metric['fulfilled_demand']/metric['realized_demand'])
        if policy=='fixed':assert plans==[];continue
        assert len(plans)==o_count
        for p,d in zip(plans,decisions):
            result=p['plan'];ctx=d['context'];o=p['origin'];diag=result['diagnostics']
            assert result['accepted'] and result['status']=='OPTIMAL' and diag['calendar_passed'] and diag['ortools_verify_solution'] and not diag['violations']
            assert all(abs(q)<1e-7 for q in diag['calendar_future_q'].values())
            for sid in suppliers:close(result['variables']['q'][sid+'|'+o],sum(x['quantity_tonnes'] for x in d['orders'] if x['supplier_id']==sid))
            if policy.startswith(('rn_','ra_')):
                scenario_rows=p['planning_scenarios'];model=scenario_rows[0]['source_model'];pool=pool_lookup[(o,model)]
                assert scenario_rows==pool['planning_records']
                verify_plan(result,ctx,settings,paths_from_rows(scenario_rows),result['provenance']['risk'])
            else:
                path={r['target_month']:r['predicted_price'] for r in p['forecasts']}
                fake={**result,'expected_cost':result['objective'],'var':result['objective'],'cvar':result['objective'],
                    'scenario_costs':[{'scenario_id':'point','probability':1.,'components':result['components'],'total_cost':result['objective']}]}
                verify_plan(fake,ctx,settings,[('point',1.,path)],{'alpha':.9,'risk_weight':0.},False)
            checked+=1
    for model in ('sarimax','lightgbm'):assert [r['planning_scenarios'] for r in plans_all['rn_'+model]]==[r['planning_scenarios'] for r in plans_all['ra_'+model]]
    for pair in read(target/'paired.json'):
        a,b=ledgers[pair['left']],ledgers[pair['right']]
        close(pair['cost_difference'],sum(float(x['total_cost'])-float(y['total_cost']) for x,y in zip(a,b) if pair['period']=='full' or x['period']==pair['period']))
    assert checked==solves
    return {'policies':7,'decisions':o_count*7,'ledger_rows':n*7,'plans':checked}


def verify(directory: Path) -> dict:
    with integration_source_guard(ROOT) as access:
        manifest=read(directory/'run_manifest.json');assert manifest['complete']
        for name,expected in manifest['outputs'].items():assert sha(directory/name)==expected
        fixture=ROOT/manifest['synthetic_directory']
        for name,expected in manifest['synthetic_outputs'].items():assert sha(fixture/name)==expected
        observations=read(fixture/'observations.json');prices={r['observation_month']:r['price'] for r in observations};publication={r['observation_month']:r['actual_available_at'] for r in observations}
        assert all(r['knowledge_type']=='synthetic_day12_not_world_bank' for r in observations)
        # Reconstruct the preregistered synthetic process, without the generator function.
        rng=Random(20261030);deltas=[];level=200
        for i,r in enumerate(observations):
            d=.1+(.35*deltas[i-1] if i else 0)+(.25*deltas[i-12] if i>=12 else 0)-(.0875*deltas[i-13] if i>=13 else 0)+rng.gauss(0,1.5)
            deltas.append(d);level+=d;close(r['price'],level,1e-10)
        by_month={r['observation_month']:r for r in observations};seen=set();last_publication=''
        for release in zipped(directory/'release_log.json.gz'):
            month=release['observation_month'];original=dict(by_month[month])
            assert month not in seen and month<release['released_at_origin']
            assert release['actual_available_at']<=endstamp(release['released_at_origin'])
            assert release['actual_available_at']>=last_publication
            seen.add(month);last_publication=release['actual_available_at']
            original['observation_month']=date.fromisoformat(month+'-01');original['actual_available_at']=datetime.fromisoformat(original['actual_available_at'])
            assert value_hash(original)==release['observation_sha256']
        specs=tomllib.loads((ROOT/'configs/forecasting/models.toml').read_text(encoding='utf-8'))
        issued={}
        for p in sorted((directory/'issuances').glob('*.json')):
            value=read(p);digest=value.pop('issued_sha256');assert value_hash(value)==digest
            origin=value['origin'];proof=value['proof'];model=value['raw'][0]['model_name'];issued[(origin,model)]=(value,digest)
            assert value['backend_kind']=='native_statsmodels_lightgbm' and value['knowledge_type']=='synthetic_day12_not_world_bank'
            assert origin not in ('2024-06','2024-07','2024-08')
            assert index(proof['information_cutoff'])==index(origin)-1 and index(proof['training_origin_end'])<=index(origin)-4
            assert index(proof['last_complete_training_target'])<=index(origin)-1 and proof['max_training_available_at']<=endstamp(origin)
            assert proof['model_spec_sha256']==value_hash(specs[value['label']]) and proof['feature_count']==15
            history=[{'month':date.fromisoformat(m+'-01'),'price':r['price'],'unit':r['unit'],
                'available_at':datetime.fromisoformat(r['actual_available_at'])} for m,r in sorted(by_month.items())
                if m<origin and r['actual_available_at']<=endstamp(origin)]
            assert value_hash(history)==proof['history_sha256']
            assert all(e['status']=='success' for e in value['events'])
            if value['label']=='sarimax':assert len(value['events'])==1 and value['events'][0]['converged']
            else:
                assert len(value['events'])==12
                assert [e['quantile'] for e in value['events']]==[None,.1,.5,.9]*3
            for h,row in enumerate(value['raw'],1):
                assert row['horizon']==h and index(row['target_month'])==index(origin)+h and row['steps_from_latest_observation']==h+1
                assert row['fit_max_label_available_at']<=endstamp(origin) and index(row['fit_information_end'])<=index(origin)-1
                assert all(row[k]>0 for k in ('point_prediction','q10','q50','q90','lower_bound','upper_bound'))
        assert len(issued)==236
        released=zipped(directory/'oof_released.json.gz');release_lookup={r['issuance_sha256']:r for r in released}
        for r in released:
            raw,digest=issued[(r['source_origin'],r['model'])]
            assert r['issuance_sha256']==digest and index(r['source_origin'])+3<=index(r['first_released_at_origin'])-1
            for i,p in enumerate(raw['raw']):
                target=p['target_month'];assert publication[target]<=endstamp(r['first_released_at_origin'])
                close(r['actual_prices'][i],prices[target]);close(r['ratios'][i],prices[target]/p['point_prediction'])
                expected=max(p['lower_bound']-prices[target],prices[target]-p['upper_bound'],0)
                if r['scores'][i] is not None:close(r['scores'][i],expected)
        for row in zipped(directory/'calibration_audit.json.gz'):
            selected=[release_lookup[k] for k in row['selected_issuances']];i=row['horizon']-1
            eligible=sorted((r for r in released if r['model']==row['model'] and r['first_released_at_origin']<=row['origin'] and r['scores'][i] is not None),key=lambda r:r['targets'][i])[-60:]
            assert [r['issuance_sha256'] for r in selected]==[r['issuance_sha256'] for r in eligible]
            n=len(selected);rank=__import__('math').ceil((n+1)*.8);assert row['rank']==rank and row['count']==n and n<=60
            if row['status']=='calibrated':assert n>=24;close(row['adjustment'],sorted(r['scores'][i] for r in selected)[rank-1])
        cal_lookup={(r['origin'],r['model'],r['horizon']):r for r in zipped(directory/'calibration_audit.json.gz')}
        for row in zipped(directory/'calibrated.json.gz'):
            key=row['forecast_origin'],row['model_name'],row['horizon'];audit=cal_lookup[key]
            raw=issued[key[:2]][0]['raw'][row['horizon']-1]
            close(row['point_prediction'],raw['point_prediction'])
            assert row['q10'] is row['q50'] is row['q90'] is None and row['base_q10']==raw['q10'] and row['base_q90']==raw['q90']
            if audit['status']=='raw_invalid_uncalibrated':assert row['lower_bound'] is row['upper_bound'] is None
            else:
                delta=audit['adjustment'] or 0
                close(row['lower_bound'],raw['lower_bound']-delta);close(row['upper_bound'],raw['upper_bound']+delta)
        pools=zipped(directory/'pool_audit.json.gz');lookup={}
        for row in pools:
            o=row['origin'];model=row['model'];vectors=row['vectors'];lookup[(o,model)]=row
            eligible=sorted((v for v in released if v['model']==model and v['first_released_at_origin']<=o),key=lambda v:v['source_origin'])[-60:]
            assert vectors==eligible and 24<=len(vectors)<=60 and row['evaluation_rejected']
            normal=[]
            for v in vectors:
                x=dict(v)
                for k in ('source_origin','first_released_at_origin'):x[k]=date.fromisoformat(x[k]+'-01')
                for k in ('targets','fit_information_end'):x[k]=tuple(date.fromisoformat(m+'-01') for m in x[k])
                for k in ('actual_available_at','fit_max_label_available_at'):x[k]=tuple(datetime.fromisoformat(s) for s in x[k])
                normal.append(x)
            assert value_hash(tuple(normal))==row['pool_sha256']
            seed=int.from_bytes(hashlib.sha256(f'2026102901|{o}|{model}|planning'.encode()).digest()[:16],'big');assert str(seed)==row['planning_seed']
            rng=Random(seed);points=issued[(o,model)][0]['raw'];scenario_rows=row['planning_records']
            assert len(scenario_rows)==384 and sum(r['probability'] for r in scenario_rows if r['horizon']==1)==1
            for i in range(128):
                vector=vectors[rng.randrange(len(vectors))]
                for h,r in enumerate(scenario_rows[i*3:i*3+3]):
                    assert r['source_oof_origin']==vector['source_origin'];close(r['price'],points[h]['point_prediction']*vector['ratios'][h])
        final=verify_calendar(directory,fixture,prices,lookup,'final_shape',(22,24,21,132))
        validation=verify_calendar(directory,fixture,prices,lookup,'validation_shape',(36,38,35,216))
        assert not access['blocked_attempts']
        return {'passed':True,'directory':directory.relative_to(ROOT).as_posix(),'run_manifest_sha256':sha(directory/'run_manifest.json'),
            'final_shape':final,'validation_shape':validation,'issuances_checked':len(issued),
            'complete_oof_vectors_checked':len(released),'pool_audits_checked':len(pools),'actual_source_opens':0}


def compare_runs(first: Path,second: Path) -> dict:
    with integration_source_guard(ROOT) as access:
        a,b=read(first/'run_manifest.json'),read(second/'run_manifest.json')
        assert a['code_at_start']==b['code_at_start'] and a['config_sha256']==b['config_sha256']
        assert a['outputs'].keys()==b['outputs'].keys() and a['synthetic_outputs']==b['synthetic_outputs']
        equal=0
        for name in a['outputs']:
            assert sha(first/name)==a['outputs'][name] and sha(second/name)==b['outputs'][name]
            if name=='summary.json':
                x,y=read(first/name),read(second/name);x.pop('synthetic_directory');y.pop('synthetic_directory');assert x==y
            else:assert (first/name).read_bytes()==(second/name).read_bytes();equal+=1
        for name in a['synthetic_outputs']:
            x,y=ROOT/a['synthetic_directory']/name,ROOT/b['synthetic_directory']/name
            assert x.read_bytes()==y.read_bytes();equal+=1
        return {'passed':True,'canonical_run':first.relative_to(ROOT).as_posix(),'repeat_run':second.relative_to(ROOT).as_posix(),
            'canonical_run_manifest_sha256':sha(first/'run_manifest.json'),'repeat_run_manifest_sha256':sha(second/'run_manifest.json'),
            'deterministic_files_byte_equal':equal,'summary_equal_after_removing_run_path':True,
            'numeric_tolerance_required':False,'declared_price_tolerance':1e-8,
            'excluded':['native_timing.json','solver_timing.json','run_manifest.json paths','summary.json synthetic directory path'],
            'actual_source_opens':access['actual_source_opens']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--repeat',type=Path);a=p.parse_args()
    result=compare_runs(a.directory.resolve(),a.repeat.resolve()) if a.repeat else verify(a.directory.resolve())
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
