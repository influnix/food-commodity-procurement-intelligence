"""Read-only saved-evidence closeout. No model, solver, source loader or experiment calls."""

import argparse
import builtins
from calendar import monthrange
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
D3='artifacts/day3/20261027T013028732383Z'
D4={'sarimax':'artifacts/day4/sarimax_20261027T021556181229Z','lightgbm':'artifacts/day4/lightgbm_20261027T021556175230Z'}
D9='artifacts/day9/20261030T090528446877Z'
D10='artifacts/day10/run_20261030T114444326360Z'
DAY12='artifacts/day12/candidate_20261030T153217902819Z.json'
DAY12_SHA='ae093042b0cfbe3b8af5a75d01e235f12faa5adb82fd0438527286a0006b6a4f'


@contextmanager
def no_data_access(root: Path):
    """Deny all workspace data opens, including synthetic data; permit metadata stat."""
    data=(root/'data').resolve();audit={'actual_source_opens':0,'blocked_attempts':[]}
    def wrap(original):
        def guarded(file,*args,**kwargs):
            if not isinstance(file,int):
                try:p=Path(os.fsdecode(file)).resolve()
                except (TypeError,ValueError):p=None
                if p is not None and p.is_relative_to(data):
                    audit['blocked_attempts'].append(p.relative_to(root).as_posix())
                    raise PermissionError('Day13 permits saved evidence only; no data-directory opens')
            return original(file,*args,**kwargs)
        return guarded
    with patch('builtins.open',wrap(builtins.open)),patch('io.open',wrap(io.open)),patch('os.open',wrap(os.open)):
        yield audit


def sha(path: Path) -> str:return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path: Path):return json.loads(path.read_text(encoding='utf-8'))
def rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def save(path: Path,value) -> None:path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def csv_save(path: Path,values: list[dict]) -> None:
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
def close(a: float,b: float) -> None:
    if not math.isfinite(a) or not math.isfinite(b) or not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-6):raise ValueError(f'Evidence mismatch {a} != {b}')
def index(m: str) -> int:y,n=map(int,m.split('-'));return y*12+n-1
def month(i: int) -> str:return f'{i//12:04d}-{i%12+1:02d}'
def stamp(m: str) -> str:
    y,n=map(int,m.split('-'));return f'{m}-{monthrange(y,n)[1]:02d}T23:59:59+00:00'


class References:
    def __init__(self,root: Path):self.root=root;self.files={}
    def add(self,name: str,role: str,expected: str|None=None) -> Path:
        p=(self.root/name).resolve()
        if not p.is_relative_to(self.root.resolve()) or p.is_relative_to((self.root/'data').resolve()):raise PermissionError('Only non-data references allowed')
        h=sha(p)
        if expected is not None and h!=expected:raise ValueError('Saved upstream hash changed: '+name)
        self.files[name]={'path':name,'sha256':h,'size_bytes':p.stat().st_size,'role':role}
        return p
    def artifact(self,directory: str,name: str,manifest: dict,role: str) -> Path:
        full=directory+'/'+name;expected=manifest['output_sha256'].get(name,manifest['output_sha256'].get(full))
        if expected is None:raise ValueError('Artifact absent from upstream manifest: '+full)
        return self.add(full,role,expected)


def forecast_summary(values: list[dict]) -> list[dict]:
    keys=set();actuals={};scales={}
    for r in values:
        o,t,h=r['forecast_origin'],r['target_month'],int(r['horizon'])
        if not '2021-06'<=o<='2024-05' or not '2021-07'<=t<='2024-08':raise ValueError('Non-validation forecast key')
        if index(t)!=index(o)+h or r['information_cutoff']!=month(index(o)-1) or h not in (1,2,3):raise ValueError('Forecast timing mismatch')
        if r['forecast_asof_at']!=stamp(o) or int(r['steps_from_latest_observation'])!=h+1 or r['unit']!='USD_per_metric_tonne':raise ValueError('Forecast clock/unit mismatch')
        key=o,h
        if key in keys:raise ValueError('Duplicate forecast key')
        keys.add(key);p,y,s=(float(r[k]) for k in ('predicted_price','actual_price','mase_scale'))
        if min(p,y,s)<=0 or not all(math.isfinite(v) for v in (p,y,s)):raise ValueError('Invalid forecast/scale')
        close(float(r['absolute_error']),abs(y-p));close(float(r['scaled_error']),abs(y-p)/s)
        if t in actuals:close(actuals[t],y)
        actuals[t]=y
        if o in scales:close(scales[o],s)
        scales[o]=s
    expected={(month(i),h) for i in range(index('2021-06'),index('2024-05')+1) for h in (1,2,3)}
    if keys!=expected:raise ValueError('Incomplete36x3 forecast grid')
    summaries=[]
    for h in (0,1,2,3):
        selected=[r for r in values if not h or int(r['horizon'])==h]
        summaries.append({'model':values[0]['model_name'],'horizon':'overall' if not h else str(h),'n':len(selected),
            'mae':math.fsum(abs(float(r['actual_price'])-float(r['predicted_price'])) for r in selected)/len(selected),
            'mase':math.fsum(abs(float(r['actual_price'])-float(r['predicted_price']))/float(r['mase_scale']) for r in selected)/len(selected)})
    return summaries


COSTS=('procurement_cost','transport_cost','holding_cost','unmet_cost','disposal_cost','terminal_cost','total_cost')


def audit_policy(ledger: list[dict],orders: list[dict],receipts: list[dict],prices: dict[str,float]) -> tuple[list[dict],dict]:
    months=[month(i) for i in range(index('2021-07'),index('2024-08')+1)]
    if [r['month'] for r in ledger]!=months:raise ValueError('Incomplete38-month ledger')
    if len({r['order_id'] for r in orders})!=len(orders) or len(receipts)!=len(orders):raise ValueError('Duplicate/missing order or receipt')
    receipt_map={r['order_id']:r for r in receipts}
    if set(receipt_map)!={r['order_id'] for r in orders}:raise ValueError('Receipt order identity mismatch')
    supplier={'A':(2,80.,.02),'B':(1,100.,.08)};cohorts={};allocation={'A':0.,'B':0.}
    for o in orders:
        sid,k,q=o['supplier_id'],o['order_month'],float(o['quantity_tonnes']);lead,cap,premium=supplier[sid]
        if not '2021-06'<=k<='2024-05' or q<=0 or o['initial_pipeline']!='False':raise ValueError('Out-of-calendar/invalid order')
        key=sid,k;cohorts[key]=cohorts.get(key,0)+q
        if cohorts[key]>cap+1e-7:raise ValueError('Capacity violation')
        allocation[sid]+=q;r=receipt_map[o['order_id']];arrival=month(index(k)+lead)
        if r['receipt_month']!=arrival or r['promised_month']!=arrival or index(arrival)+1>index('2024-08'):raise ValueError('Receipt lead/terminal mismatch')
        close(float(r['quantity_tonnes']),q);close(float(r['market_price']),prices[arrival])
        close(float(r['unit_procurement_cost']),prices[arrival]*(1+premium));close(float(r['procurement_cost']),q*prices[arrival]*(1+premium))
        if r['cost_recognized_at']!=stamp(arrival):raise ValueError('Receipt recognition mismatch')
    inventory=200.
    for r in ledger:
        m=r['month'];incoming=[x for x in receipts if x['receipt_month']==m]
        close(float(r['beginning_inventory']),inventory);received=math.fsum(float(x['quantity_tonnes']) for x in incoming)
        available=inventory+received;served=min(available,100.);unmet=100.-served;waste=max(available-served-400.,0.);inventory=available-served-waste
        for k,v in (('received_quantity',received),('available_inventory',available),('realized_demand',100.),('fulfilled_demand',served),('unmet_demand',unmet),('disposed_quantity',waste),('ending_inventory',inventory)):close(float(r[k]),v)
        costs={'procurement_cost':math.fsum(float(x['procurement_cost']) for x in incoming),'transport_cost':0.,'holding_cost':inventory*3.,'unmet_cost':unmet*1500.,'disposal_cost':waste,'terminal_cost':abs(inventory-200.)*9. if m=='2024-08' else 0.}
        costs['total_cost']=math.fsum(costs.values())
        for k,v in costs.items():close(float(r[k]),v)
        outstanding=math.fsum(float(o['quantity_tonnes']) for o in orders if o['order_month']<=m and month(index(o['order_month'])+supplier[o['supplier_id']][0])>m)
        close(float(r['outstanding_quantity']),outstanding)
        close(float(r['new_order_quantity']),math.fsum(float(o['quantity_tonnes']) for o in orders if o['order_month']==m))
        if m>'2024-05' and float(r['new_order_quantity'])!=0:raise ValueError('Runoff order')
        if r['period']!=('active' if m<='2024-05' else 'runoff'):raise ValueError('Period mismatch')
    close(float(ledger[-1]['outstanding_quantity']),0)
    result=[]
    for period in ('full','active','runoff'):
        selected=[r for r in ledger if period=='full' or r['period']==period]
        totals={k:math.fsum(float(r[k]) for r in selected) for k in COSTS}
        demand=math.fsum(float(r['realized_demand']) for r in selected);served=math.fsum(float(r['fulfilled_demand']) for r in selected)
        result.append({'period':period,'months':len(selected),**totals,'demand_tonnes':demand,'fulfilled_tonnes':served,
            'unmet_tonnes':demand-served,'fill_rate':served/demand,'average_inventory':math.fsum(float(r['ending_inventory']) for r in selected)/len(selected)})
    return result,allocation


def make_plot(output: Path,monthly: list[dict]) -> dict:
    os.environ['MPLCONFIGDIR']=str(ROOT/'artifacts/day13/render_cache')
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    figure=Figure(figsize=(10,4),dpi=150);FigureCanvasAgg(figure);axis=figure.subplots()
    for policy,title,color in (('fixed','Fixed','#2467a6'),('fa_sarimax','Forecast-Aware SARIMAX','#cd7225')):
        selected=[r for r in monthly if r['policy']==policy]
        axis.plot(range(38),[r['ending_inventory'] for r in selected],label=title,color=color,linewidth=1.8,marker='.',markersize=4)
    axis.axvspan(34.5,37.5,color='#eeeeee',label='Runoff (Jun-Aug 2024)');axis.set_xlim(-.5,37.5)
    ticks=list(range(0,38,3))+[37];labels=[monthly[i]['month'] for i in ticks]
    axis.set_xticks(ticks,labels,rotation=45,ha='right');axis.set_ylabel('Month-end inventory (tonnes)')
    axis.set_title('Stored Validation ledger: lower inventory did not ensure lower full cost')
    axis.grid(axis='y',alpha=.2);axis.legend(loc='upper right',fontsize=8);figure.tight_layout()
    figure.savefig(output/'monthly_inventory.png',metadata={'Software':'Day13 saved-evidence report; Matplotlib '+matplotlib.__version__})
    return {'matplotlib':matplotlib.__version__,'source':'monthly_ledger_summary.csv','new_experiment':False}


def build(root: Path,output: Path,plot: bool=True) -> dict:
    root=root.resolve();output=output.resolve()
    if not output.is_relative_to(root/'artifacts/day13') or output.exists():raise ValueError('New Day13-only output directory required')
    output.mkdir(parents=True)
    with no_data_access(root) as access:
        ref=References(root);forecast=[];raw_models={}
        baseline=read(ref.add(D3+'/run_manifest.json','saved baseline provenance'))
        catalogs=[(D3,baseline,'validation_predictions.csv')]
        for label,directory in D4.items():catalogs.append((directory,read(ref.add(directory+'/manifest.json','saved native model provenance')),'predictions.csv'))
        for directory,manifest,filename in catalogs:
            values=rows(ref.artifact(directory,filename,manifest,'stored Validation predictions; no new forecasts'))
            summary=forecast_summary(values);metrics=read(ref.artifact(directory,'metrics.json',manifest,'stored forecast metrics'))
            for r in summary:
                old=metrics['overall'] if r['horizon']=='overall' else metrics['by_horizon'][r['horizon']]
                close(r['mae'],old['mae']);close(r['mase'],old['mase'])
            forecast.extend(summary);raw_models[values[0]['model_name']]=values
        base=next(r for r in forecast if r['horizon']=='overall' and r['model']=='seasonal_naive_12')
        for r in forecast:
            r['baseline_overall_mae_improvement_pct']=(base['mae']-r['mae'])/base['mae']*100 if r['horizon']=='overall' else ''
        for values in raw_models.values():
            for i,r in enumerate(values):
                other=next(iter(raw_models.values()))[i]
                if (r['forecast_origin'],r['horizon'])!=(other['forecast_origin'],other['horizon']):raise ValueError('Model key mismatch')
                close(float(r['actual_price']),float(other['actual_price']));close(float(r['mase_scale']),float(other['mase_scale']))
        m9=read(ref.add(D9+'/manifest.json','original historical-price/synthetic-operations evaluation'))
        evaluation=rows(ref.artifact(D9,'evaluation_prices.csv',m9,'stored38-month Validation evaluator output'))
        if [r['observation_month'] for r in evaluation]!=[month(i) for i in range(index('2021-07'),index('2024-08')+1)]:raise ValueError('Non-validation evaluation prices')
        prices={r['observation_month']:float(r['price']) for r in evaluation}
        original_metrics=read(ref.artifact(D9,'policy_metrics.json',m9,'original seven-policy metrics'))
        monthly=[];policies=[];orders_summary=[];ledger_map={};plans={};decisions={}
        for policy in ('fixed','fa_sarimax'):
            ledger,orders,receipts=(rows(ref.artifact(D9,policy+'_'+k+'.csv',m9,'stored '+policy+' '+k)) for k in ('ledger','orders','receipts'))
            summaries,allocation=audit_policy(ledger,orders,receipts,prices);ledger_map[policy]=ledger
            for r in summaries:
                original=next(x for x in original_metrics if x['policy']==policy and x['period']==r['period'])
                for k in COSTS:close(r[k],original[k])
                close(r['fill_rate'],original['fill_rate']);close(r['unmet_tonnes'],original['unmet_demand'])
                policies.append({'policy':policy,**r})
            orders_summary.extend({'policy':policy,'supplier':sid,'ordered_tonnes':q} for sid,q in allocation.items())
            monthly.extend({'policy':policy,'month':r['month'],'period':r['period'],**{k:float(r[k]) for k in (*COSTS,'beginning_inventory','ending_inventory','received_quantity','new_order_quantity','unmet_demand','outstanding_quantity')}} for r in ledger)
            decisions[policy]=read(ref.artifact(D9,policy+'_decision_audit.json',m9,'stored36 decisions'))
            plans[policy]=read(ref.artifact(D9,policy+'_rolling_plans.json',m9,'stored planning diagnostic; no new optimization'))
            if len(decisions[policy])!=36 or policy!='fixed' and len(plans[policy])!=36:raise ValueError('Incomplete policy origin evidence')
        fixed=next(r for r in policies if r['policy']=='fixed' and r['period']=='full');fa=next(r for r in policies if r['policy']=='fa_sarimax' and r['period']=='full')
        close(fixed['total_cost'],1351501.68);close(fa['total_cost'],1365914.16)
        difference={k:fa[k]-fixed[k] for k in COSTS};difference['cost_difference_pct']=difference['total_cost']/fixed['total_cost']*100
        difference['unmet_difference_tonnes']=fa['unmet_tonnes']-fixed['unmet_tonnes'];close(difference['total_cost'],14412.48)
        context=decisions['fa_sarimax'][-1]['context'];last=plans['fa_sarimax'][-1]['plan']
        bound=context['on_hand_tonnes']+sum(o['quantity_tonnes'] for o in context['outstanding_orders'])+sum(s['monthly_capacity_tonnes'] for s in context['suppliers'])
        close(bound,280.);close(last['variables']['U']['2024-08'],20.)
        diagnosis={'last_origin':'2024-05','on_hand':context['on_hand_tonnes'],'existing_pipeline':sum(o['quantity_tonnes'] for o in context['outstanding_orders']),
            'maximum_current_orders':180.,'runoff_demand':300.,'maximum_supply_from_last_state':bound,'unavoidable_shortage_from_this_state':300-bound,
            'shortage_already_in_saved_plan':20.,'shortage_month':'2024-08','components_fa_minus_fixed':difference,
            'causal_limit':'Accounting and last-state feasibility explain this stored run; no counterfactual establishes forecast error as the sole cause.'}
        csv_save(output/'forecast_comparison.csv',forecast);csv_save(output/'policy_comparison.csv',policies)
        csv_save(output/'supplier_allocation.csv',orders_summary);csv_save(output/'monthly_ledger_summary.csv',monthly);save(output/'cost_service_diagnosis.json',diagnosis)
        ref.artifact(D9,'completeness.json',m9,'seven-policy completion and failures')
        for name in ('docs/WORLD_BANK_SOURCE.md','configs/splits.toml','configs/day3.toml','configs/day4.toml','configs/day9.toml','configs/day10.toml',
            'docs/DAY4_MODEL_SPEC.md','docs/DAY9_EVALUATION_PROTOCOL.md','docs/DAY10_STATUS.md','docs/DAY11_PRE_HOLDOUT_PROTOCOL.md','docs/DAY11_LIMITATIONS.md',
            'docs/DAY12_STATUS.md','docs/DAY12_RELEASE_READINESS.md','artifacts/day12/uncertainty_diagnostics.json','artifacts/day12/calibration_fallback_probe.json',
            'artifacts/day10/final_qa.json','artifacts/day12/test_results.json',D10+'/policy_matrix.csv'):
            ref.add(name,'provenance, extension or methodological limitation reference')
        ref.add(DAY12,'preserved candidate; not an approval for Day13 changes',DAY12_SHA)
        for name in ('src/food_procurement_intelligence/features/price.py','src/food_procurement_intelligence/forecasting/sarimax.py',
            'src/food_procurement_intelligence/evaluation/model_backtesting.py','src/food_procurement_intelligence/policies/fixed.py',
            'src/food_procurement_intelligence/policies/forecast_aware.py','src/food_procurement_intelligence/optimization/deterministic.py',
            'src/food_procurement_intelligence/simulation/engine.py','scripts/build_day13_evidence.py','scripts/verify_day13_evidence.py',
            'scripts/run_day13_tests.py','tests/test_day13_evidence.py'):
            ref.add(name,'implementation trace or Day13 read-only verification')
        for name in ('docs/MVP_SCOPE.md','docs/MVP_ACCEPTANCE_REPORT.md','docs/MVP_RESULTS.md','docs/ARCHITECTURE_OVERVIEW.md','docs/REPRODUCIBILITY.md','README.md','docs/ROADMAP.md'):
            ref.add(name,'MVP portfolio documentation; preserved history with Day13 entry')
        test_path=root/'artifacts/day13/test_results.json'
        tests=read(ref.add('artifacts/day13/test_results.json','current complete regression')) if test_path.exists() else {'passed':False}
        if not tests.get('passed') or tests.get('previous_tests')!=403:raise ValueError('Fresh403-test regression evidence required')
        save(output/'test_evidence.json',tests)
        acceptance=[]
        for code,requirement,module,evidence,result,limit in (
          ('MVP-01','Monthly commodity price forecasts','forecasting/sarimax.py; forecasting/lightgbm.py','forecast_comparison.csv','SARIMAX/LightGBM108 saved predictions each; metrics independently recomputed','Latest-vintage pseudo-real-time; validation selection bias'),
          ('MVP-02','Rolling-origin backtest','evaluation/model_backtesting.py; features/price.py','forecast_comparison.csv','36 origins; H1/H2/H3; t-1 cutoff and matching actuals/scales','MASE denominator reused from pinned fold output; no raw recomputation today'),
          ('MVP-03','Same-condition comparison of two policies','policies/fixed.py; policies/forecast_aware.py; evaluation/policy_backtest.py','policy_comparison.csv','38 months; FA minus Fixed +14412.48USD;20t shortage','Synthetic operations; no savings claim'),
          ('MVP-04','Traceable tests/data/forecast/decision/cost','data/availability.py; simulation/engine.py','reference_hash_index.json','Pinned manifests, orders, receipts, ledger, context and tests linked','Original price bytes not reopened; prior source hash reused'),
          ('MVP-05','Reproducible execution or saved-result verification','scripts/build_day13_evidence.py; scripts/verify_day13_evidence.py','test_evidence.json','Stored-result recomputation; companion verifier checks deterministic repeat','Evidence release only; no new model/policy experiment or Holdout authorization')):
            acceptance.append({'requirement_id':code,'mvp_requirement':requirement,'implementation_module':module,'evidence_artifact':evidence,
                'verification_method':'saved CSV/JSON arithmetic, source hash and regression checks','observed_result':result,'status':'PASS','limitation':limit})
        csv_save(output/'acceptance_matrix.csv',acceptance);save(output/'acceptance_matrix.json',acceptance)
        save(output/'data_model_provenance.json',{'source':'World Bank Pink Sheet Wheat US HRW','unit':'nominal USD/metric tonne',
            'source_period_from_prior_verified_metadata':'1960-01..2026-09;801 observations','source_raw_sha256':m9['raw_sha256'],
            'raw_bytes_reopened':False,'split':'configs/splits.toml','forecast_origins':'2021-06..2024-05;36',
            'target_horizons':'t+1/t+2/t+3; latest observation t-1 => model steps2/3/4','holdout':'2024-10..2026-09 LOCKED; bridge2024-09 excluded',
            'mvp_policies':['fixed','fa_sarimax'],'final_holdout_policy_contract':'seven policies unchanged',
            'original_day12_candidate_sha256':DAY12_SHA,'old_candidate_authorizes_day13_code':False,'actual_holdout_execution_allowed':False})
        save(output/'plot_environment.json',make_plot(output,monthly) if plot else {'plot_enabled':False,'standard_library_tables_complete':True})
        limitations=['Latest revised snapshot; no historical vintages or verified release timestamps','2020-07 HRW definition boundary',
            'Single commodity and synthetic demand/supplier/inventory/cost assumptions','Validation-based model selection; Day10 sensitivity is post-hoc',
            'Forecast accuracy does not ensure procurement savings; FA was worse in the representative comparison',
            'Day5 horizon-specific vs Day12 full-vector calibration eligibility remains a methodological consistency review',
            'Day12 synthetic LGB crossing14; current invalid13; min24 raw fallback preserved; no repair',
            'New-origin real World Bank native fitting and original seed source connection not verified',
            'Coverage below80%; empirical scenarios/CVaR do not guarantee market risk or independent/OOS performance',
            'Three-month planning, conservative no-disposal constraint, runoff and terminal approximation',
            'Holdout unassessed and locked; future work requires separate review and authorization']
        save(output/'scientific_limitations.json',limitations)
        (output/'REPRODUCTION.md').write_text('Saved-evidence rebuild only; run from project root.\n\n` .\\.venv\\Scripts\\python.exe scripts/build_day13_evidence.py --output artifacts/day13/evidence_a `\n\nUse a new output directory for each repeat. `--no-plot` permits standard-library-only tabular reproduction. Run `scripts/verify_day13_evidence.py` for independent checks. No source data, fitting, solver calls or Holdout evaluation are performed.\n',encoding='utf-8')
        save(output/'source_access_audit.json',access);save(output/'reference_hash_index.json',list(ref.files.values()))
        save(output/'evidence_release_manifest.json',{'kind':'MVP_SAVED_EVIDENCE_RELEASE_NOT_HOLDOUT_FREEZE','mvp_status':'COMPLETE',
            'requirements_passed':5,'references':list(ref.files.values()),'outputs':{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()},
            'day12_candidate_sha256':DAY12_SHA,'old_candidate_valid_for_added_day13_code':False,'holdout_locked':True,
            'actual_source_opens':0,'new_experiments':False,'actual_holdout_execution_allowed':False})
        return {'output':output.relative_to(root).as_posix(),'mvp_status':'COMPLETE','requirements_passed':5,
            'reference_files':len(ref.files),'evidence_release_sha256':sha(output/'evidence_release_manifest.json'),'actual_source_opens':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--no-plot',action='store_true');args=parser.parse_args()
    print(json.dumps(build(ROOT,args.output,not args.no_plot),indent=2))
