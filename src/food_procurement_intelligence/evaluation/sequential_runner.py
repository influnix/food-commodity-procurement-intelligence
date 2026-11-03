"""Calendar-agnostic synthetic integration using native publishers and unchanged policy cores."""

from dataclasses import asdict,dataclass
from datetime import date,datetime
import json
from pathlib import Path
from random import Random

from food_procurement_intelligence.data.sequential import Observation,SequentialObservationStore,SessionPermit
from food_procurement_intelligence.data.availability import VisiblePrice
from food_procurement_intelligence.data.world_bank import assumed_available_at
from food_procurement_intelligence.evaluation.day9 import POLICIES,PAIRS
from food_procurement_intelligence.evaluation.day6 import _serializable
from food_procurement_intelligence.evaluation.policy_inputs import PreparedPolicyInputs,make_policy
from food_procurement_intelligence.evaluation.policy_backtest import run_historical_policy,period_metrics,paired_comparison
from food_procurement_intelligence.evaluation.splits import ForecastSample,add_months,months_between,parse_month_label,decision_at
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher,without_timing
from food_procurement_intelligence.simulation.contracts import SimulationSettings,Supplier,ToyWorld
from food_procurement_intelligence.uncertainty.sequential import SequentialOOF


@dataclass(frozen=True)
class EvaluationCalendar:
    first_origin: date
    last_origin: date
    last_ledger: date

    def __post_init__(self):
        if self.first_origin>self.last_origin or add_months(self.last_origin,3)!=self.last_ledger:
            raise ValueError('Complete three-target calendar required')

    @property
    def origins(self):return months_between(self.first_origin,self.last_origin)
    @property
    def first_ledger(self):return add_months(self.first_origin,1)
    @property
    def ledger(self):return months_between(self.first_ledger,self.last_ledger)
    def record(self):
        return {'first_origin':self.first_origin,'last_origin':self.last_origin,'last_ledger':self.last_ledger,
            'origins':len(self.origins),'ledger_months':len(self.ledger),
            'active_months':sum(m<=self.last_origin for m in self.ledger),'runoff_months':sum(m>self.last_origin for m in self.ledger)}


def synthetic_observations(config: dict) -> tuple[Observation,...]:
    rng=Random(config['fixture_seed']);increments=[];level=200.;result=[]
    for i,m in enumerate(months_between(parse_month_label(config['fixture_start']),parse_month_label(config['last_ledger']))):
        value=.1+(.35*increments[i-1] if i>=1 else 0)+(.25*increments[i-12] if i>=12 else 0)-(.0875*increments[i-13] if i>=13 else 0)+rng.gauss(0,1.5)
        increments.append(value);level+=value
        result.append(Observation(m,level,datetime.fromisoformat(assumed_available_at(m)),
            'synthetic_assumed_month_plus_one_end','SYNTHETIC_DAY12_V1','DAY12_AR_INCREMENTS_SEED20261030'))
    return tuple(result)


def release_publications(store,observations,origin: date) -> None:
    store.advance(origin)
    selected=sorted((r for r in observations if r.observation_month not in store.calendar
        and r.observation_month<=add_months(origin,-1) and r.actual_available_at<=decision_at(origin)),
        key=lambda r:(r.actual_available_at,r.observation_month))
    for r in selected:store.publish(r)


def prepare_native_stream(config,d4,d5,d6,plan,directory: Path|None=None,observations=None,*,oof_factory=None,publisher_factory=None):
    observations=observations or synthetic_observations(config)
    permit=SessionPermit('DAY12_NATIVE_STREAM_V1',observations[0].source_id)
    store=SequentialObservationStore(permit);pool=(oof_factory or SequentialOOF)(permit,d5,d6['scenarios'],plan)
    last=parse_month_label(config['last_origin']);final_first=parse_month_label(config['first_origin'])
    candidates=tuple(ForecastSample(o,(1,2,3),tuple(add_months(o,h) for h in (1,2,3)))
        for o in months_between(add_months(observations[0].observation_month,13),last))
    publisher=(publisher_factory or NativeForecastPublisher)(d4,candidates,directory/'issuances' if directory else None)
    historical=set(months_between(parse_month_label(d5['historical_origin_start']),parse_month_label(d5['historical_origin_end'])))
    validation=set(months_between(plan.validation_origin_start,plan.validation_origin_end))
    final=set(months_between(final_first,last));issued={};scenarios={};audit=[];calibrated=[];calibration_audit=[]
    try:
        for origin in months_between(min(historical),last):
            release_publications(store,observations,origin);pool.tick(store,origin)
            phase='historical_train' if origin in historical else 'validation' if origin in validation else 'sequential_synthetic' if origin in final else None
            if phase is None:continue
            for batch in publisher.publish(store,origin):
                key=batch.label,origin;issued[key]=batch
                if phase in ('validation','sequential_synthetic'):
                    corrected,cal_audit=pool.calibrate(batch)
                    calibrated.extend(p.record() for p in corrected);calibration_audit.extend(cal_audit)
                    bundles={}
                    for purpose in ('planning','evaluation'):
                        bundle,vectors=pool.scenarios(batch,purpose);bundles[purpose]=bundle
                    scenarios[key]=bundles['planning']
                    try:bundles['evaluation'].for_policy(origin)
                    except ValueError:rejected=True
                    else:rejected=False
                    if not rejected:raise ValueError('Evaluation leakage')
                    audit.append({'origin':origin,'label':batch.label,'model':batch.raw[0].model_name,'phase':phase,
                        'pool_n':len(vectors),'vectors':vectors,'pool_sha256':bundles['planning'].pool_sha256,
                        'planning_seed':str(bundles['planning'].seed),'evaluation_seed':str(bundles['evaluation'].seed),
                        'evaluation_rejected':rejected,'planning_records':bundles['planning'].records()})
                pool.issue(batch,phase)
    finally:
        if directory:
            (directory/'native_events.json').write_text(json.dumps(_serializable(without_timing(publisher.events)),indent=2,sort_keys=True),encoding='utf-8')
            (directory/'native_timing.json').write_text(json.dumps(_serializable(publisher.events),indent=2,sort_keys=True),encoding='utf-8')
    return {'observations':observations,'store':store,'issued':issued,'scenarios':scenarios,'pool_audit':audit,
        'calibrated':calibrated,'calibration_audit':calibration_audit,'release_log':store.release_log,
        'oof_issue_log':pool.issue_log,'oof_released':list(pool.released.values()),'events':publisher.events}


def run_policy_calendar(stream: dict,calendar: EvaluationCalendar,d4: dict,d6: dict,d7: dict,d8: dict) -> dict:
    """Same core for22/24 and36/38. No source reader accepted; tagged synthetic path only."""
    models={label:d4[label]['model_name'] for label in ('sarimax','lightgbm')}
    if any(r.knowledge_type!='synthetic_day12_not_world_bank' for r in stream['observations']):raise ValueError('Synthetic path required')
    inputs=PreparedPolicyInputs(calendar.origins,models,
        {label:(lambda o,label=label:stream['issued'][(label,o)].points()) for label in models},
        lambda o,m:stream['scenarios'][(next(k for k,v in models.items() if v==m),o)])
    settings=SimulationSettings(**{k:d6['simulation'][k] for k in SimulationSettings.__dataclass_fields__})
    suppliers=tuple(Supplier(**r) for r in d6['suppliers'])
    prices=tuple(VisiblePrice(r.observation_month,r.price,r.unit,r.actual_available_at) for r in stream['observations'] if r.observation_month in calendar.ledger)
    world=ToyWorld('DAY12_NATIVE_SYNTHETIC_NOT_WORLD_BANK',calendar.first_ledger,calendar.last_ledger,prices,
        tuple((m,100.) for m in calendar.ledger))
    results={};plans={};timing=[];metrics=[]
    for name in POLICIES:
        policy=make_policy(name,inputs,settings,d7['lp'],d8['risk'],calendar.last_origin)
        result=run_historical_policy(world,settings,suppliers,policy,calendar.first_origin,calendar.last_origin,stream['store'].history_as_of)
        results[name]=result;plans[name]=getattr(policy,'history',[])
        timing.extend({'policy':name,'origin':o,'status':r.status,'solve_seconds':r.solve_seconds} for o,r in zip(calendar.origins,getattr(policy,'solutions',[])))
        if not result['complete']:break
        for period in ('full','active','runoff'):metrics.append({'policy':name,**period_metrics(result,period,suppliers)})
    complete=len(results)==7 and all(r['complete'] for r in results.values())
    monthly,paired=paired_comparison(results,PAIRS) if complete else ([],[])
    return {'complete':complete,'calendar':calendar.record(),'results':results,'plans':plans,'timing':timing,
        'metrics':metrics if complete else [],'monthly':monthly,'paired':paired,'settings':asdict(settings),
        'suppliers':[asdict(s) for s in suppliers],'input_audit':inputs.audit,
        'optimal_solves':sum(r['status']=='OPTIMAL' for r in timing),'fallback_count':0}
