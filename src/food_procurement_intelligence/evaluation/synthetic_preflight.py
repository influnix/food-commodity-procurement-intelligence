"""Day11 fixture-only sequential harness. Never loads or unlocks market data."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
from random import Random

from food_procurement_intelligence.data.availability import VisiblePrice, assert_feature_available
from food_procurement_intelligence.data.world_bank import assumed_available_at
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample, LeakageError, add_months, assert_training_available, decision_at, months_between,
)
from food_procurement_intelligence.evaluation.policy_inputs import PreparedPolicyInputs, make_policy, record_hash
from food_procurement_intelligence.evaluation.policy_backtest import run_historical_policy, period_metrics
from food_procurement_intelligence.evaluation.historical_backtest import POLICIES
from food_procurement_intelligence.features.price import FeatureSpec
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.forecasting.sarimax import fit_predict as sarimax_predict
from food_procurement_intelligence.forecasting.lightgbm import fit_predict as lightgbm_predict
from food_procurement_intelligence.simulation.contracts import SimulationSettings, Supplier, ToyWorld
from food_procurement_intelligence.uncertainty.calibration import finite_sample_adjustment
from food_procurement_intelligence.uncertainty.joint_scenarios import PricePath, ScenarioSet, derived_seed


@dataclass(frozen=True)
class SyntheticObservation:
    observation_month: date
    price: float
    available_at: datetime
    availability_basis: str = 'synthetic_assumed_lag1'
    vintage_id: str = 'SYNTHETIC_DAY11'
    knowledge_type: str = 'synthetic_preflight_not_world_bank'


class SyntheticAsOfStore:
    """Only tagged fixture objects are accepted; there is no file loader or unlock."""

    def __init__(self, observations: tuple[SyntheticObservation,...]):
        if not observations or any(type(p) is not SyntheticObservation or p.vintage_id!='SYNTHETIC_DAY11'
            or p.knowledge_type!='synthetic_preflight_not_world_bank' or p.availability_basis!='synthetic_assumed_lag1' for p in observations):
            raise ValueError('Synthetic fixture provenance required')
        self._values={p.observation_month:p for p in observations}
        if len(self._values)!=len(observations):raise ValueError('Duplicate fixture month')
        self.calendar=tuple(sorted(self._values))
        self.history_requests=[]

    def history_as_of(self, origin: date) -> tuple[VisiblePrice,...]:
        self.history_requests.append(origin)
        return tuple(VisiblePrice(m,p.price,'USD_per_metric_tonne',p.available_at) for m,p in sorted(self._values.items())
            if m<=add_months(origin,-1) and p.available_at<=decision_at(origin))

    def feature(self, month: date, origin: date) -> float:
        p=self._values[month]
        assert_feature_available((month,),origin,{month:p.available_at})
        return p.price

    def assert_training_samples_available(self, samples, evaluation_origin):
        assert_training_available(samples,evaluation_origin,{m:p.available_at for m,p in self._values.items()})

    def training_targets(self, sample, evaluation_origin):
        self.assert_training_samples_available((sample,),evaluation_origin)
        return tuple(self.feature(m,evaluation_origin) for m in sample.targets)


def fixture_observations(start: date, end: date) -> tuple[SyntheticObservation,...]:
    return tuple(SyntheticObservation(m,100.+2.*i%24,datetime.fromisoformat(assumed_available_at(m)))
                 for i,m in enumerate(months_between(start,end)))


class FakeSARIMAX:
    def __init__(self, values, **kwargs):self.last=float(values[-1])
    def fit(self, **kwargs):return self
    @property
    def mle_retvals(self):return {'converged':True,'iterations':0}
    def forecast(self,steps):
        if steps!=4:raise AssertionError('Expected four model steps')
        return [self.last]*4


def fake_lgb_trainer(values,labels,names,params,rounds):
    class Prediction:
        def predict(self,rows):
            return [float(row[names.index('lag_1')]+.25*row[names.index('forecast_horizon')]) for row in rows]
    if rounds!=100:raise AssertionError('Frozen rounds changed')
    return Prediction()


def stub_points(store: SyntheticAsOfStore, origin: date, model: str, lightgbm: bool):
    last=store.history_as_of(origin)[-1].price
    return tuple(ModelPrediction(origin,add_months(origin,-1),add_months(origin,h),h,
                                 last+.25*h if lightgbm else last,model) for h in (1,2,3))


def synthetic_pool(store: SyntheticAsOfStore, issued: dict, origin: date, current_points, model: str, config: dict):
    """Fixture math only: production OOF phase guards remain unchanged and NOT_READY."""
    history={p.month:p for p in store.history_as_of(origin)}
    vectors=[];horizon_scores={h:[] for h in (1,2,3)}
    for (source_model,past),points in sorted(issued.items()):
        if source_model!=model or past>=origin:continue
        targets=tuple(add_months(past,h) for h in (1,2,3))
        if (tuple(p.horizon for p in points)!=(1,2,3) or any(p.forecast_origin!=past or p.model_name!=model
            or p.information_cutoff!=add_months(past,-1) or p.target_month!=targets[p.horizon-1] for p in points)):
            raise LeakageError('Synthetic OOF issuance proof mismatch')
        for p in points:
            actual=history.get(p.target_month)
            if actual is not None:
                horizon_scores[p.horizon].append((p.target_month,max(.9*p.predicted_price-actual.price,actual.price-1.1*p.predicted_price,0.)))
        if any(m not in history for m in targets):continue
        if max(targets)>add_months(origin,-1):raise LeakageError('Immature synthetic joint vector')
        if any(p.information_cutoff>=p.target_month for p in points):raise LeakageError('Synthetic OOF fit leakage')
        ratios=tuple(history[p.target_month].price/p.predicted_price for p in points)
        vectors.append({'source_origin':past,'targets':targets,'ratios':ratios,
            'available_at':[history[m].available_at for m in targets],'fit_cutoff':add_months(past,-1)})
    vectors=vectors[-config['rolling']['joint_vector_window']:]
    if len(vectors)<config['rolling']['minimum_joint_vectors']:raise ValueError('Insufficient synthetic complete vectors')
    audit={'origin':origin,'model':model,'joint_pool_count':len(vectors),'vector_proofs':vectors,'calibration':{}}
    for h,values in horizon_scores.items():
        scores=[value for _,value in sorted(values)[-config['rolling']['calibration_window']:]]
        delta,k=finite_sample_adjustment(scores,.8,config['rolling']['minimum_calibration_samples'])
        audit['calibration'][str(h)]={'count':len(scores),'rank':k,'adjustment':delta,'raw_interval_fixture_only':True}
    proof=hashlib.sha256(json.dumps(vectors,sort_keys=True,default=str).encode()).hexdigest()
    bundles={}
    for purpose in ('planning','evaluation'):
        seed=derived_seed(config['rolling'][purpose+'_seed'],origin,model,purpose)
        rng=Random(seed);paths=[]
        for i in range(128):
            vector=vectors[rng.randrange(len(vectors))]
            prices=tuple(p.predicted_price*ratio for p,ratio in zip(current_points,vector['ratios']))
            paths.append(PricePath(f'{purpose}|synthetic_day11|{model}|{origin:%Y-%m}|{i:04d}',vector['source_origin'],prices,1/128))
        bundles[purpose]=ScenarioSet(origin,model,purpose,'multiplicative_joint_oof',seed,tuple(paths),proof)
    return bundles,audit


def run_synthetic_preflight(config: dict, d4: dict, d6: dict, d7: dict, d8: dict):
    from food_procurement_intelligence.evaluation.splits import parse_month_label
    c=config['calendar'];first,last=parse_month_label(c['first_origin']),parse_month_label(c['last_origin'])
    start,end=parse_month_label(c['first_ledger']),parse_month_label(c['last_ledger'])
    observations=fixture_observations(parse_month_label(config['synthetic']['fixture_start']),end)
    store=SyntheticAsOfStore(observations);origins=months_between(first,last)
    models={'sarimax':d4['sarimax']['model_name'],'lightgbm':d4['lightgbm']['model_name']}
    candidates=tuple(ForecastSample(o,(1,2,3),tuple(add_months(o,h) for h in (1,2,3)))
        for o in months_between(add_months(observations[0].observation_month,13),last))
    issued={};native_points={};fit_audit=[];pool_audit=[];bundles={};purpose_checks=[]
    for past in months_between(add_months(first,-config['synthetic']['warmup_issued_origins']),add_months(first,-1)):
        for label,model in models.items():issued[(model,past)]=stub_points(store,past,model,label=='lightgbm')
    for origin in origins:
        sample=ForecastSample(origin,(1,2,3),tuple(add_months(origin,h) for h in (1,2,3)))
        sar=sarimax_predict(store,sample,d4['sarimax'],FakeSARIMAX)
        lgb=lightgbm_predict(store,sample,d4['lightgbm'],FeatureSpec(),candidates,fake_lgb_trainer)
        if len(sar.predictions)!=3 or len(lgb.predictions)!=3:raise AssertionError('Synthetic model harness incomplete')
        for label,fold in (('sarimax',sar),('lightgbm',lgb)):
            model=models[label];native_points[(label,origin)]=fold.predictions
            available=store.history_as_of(origin)
            maturity=[s for s in candidates if s.origin<origin and max(s.targets)<=add_months(origin,-1)]
            store.assert_training_samples_available(maturity,origin)
            fit_audit.append({'origin':origin,'model':model,'knowledge_type':config['synthetic']['knowledge_type'],
                'backend':'injected_fake_no_parameter_training','history_count':len(available),'history_end':max(p.month for p in available),
                'feature_cutoff':sample.feature_cutoff,'latest_training_origin':max(s.origin for s in maturity),
                'last_training_target':max(m for s in maturity for m in s.targets),
                'max_training_available_at':max(store._values[m].available_at for s in maturity for m in s.targets),
                'steps_from_latest_observation':[2,3,4],'targets':sample.targets,
                'native_statuses':[r['status'] for r in fold.events]})
            generated,audit=synthetic_pool(store,issued,origin,fold.predictions,model,config)
            bundles[(model,origin)]=generated['planning'];pool_audit.append(audit)
            assert generated['planning'].for_policy(origin)
            try:generated['evaluation'].for_policy(origin)
            except LeakageError:rejected=True
            else:rejected=False
            assert rejected
            purpose_checks.append({'origin':origin,'model':model,'evaluation_rejected':rejected,
                'planning_seed':str(generated['planning'].seed),'evaluation_seed':str(generated['evaluation'].seed),
                'planning_hash':record_hash(generated['planning'].records()),'probability_sum':sum(p.weight for p in generated['planning'].paths)})
            issued[(model,origin)]=fold.predictions
    inputs=PreparedPolicyInputs(origins,models,{label:(lambda o,label=label:native_points[(label,o)]) for label in models},lambda o,m:bundles[(m,o)])
    settings=SimulationSettings(**{key:d6['simulation'][key] for key in SimulationSettings.__dataclass_fields__})
    suppliers=tuple(Supplier(**row) for row in d6['suppliers'])
    prices=tuple(VisiblePrice(p.observation_month,p.price,'USD_per_metric_tonne',p.available_at) for p in observations if start<=p.observation_month<=end)
    world=ToyWorld('DAY11_SYNTHETIC_NOT_WORLD_BANK',start,end,prices,tuple((m,100.) for m in months_between(start,end)))
    results={};plans={};timing=[]
    for name in POLICIES:
        policy=make_policy(name,inputs,settings,d7['lp'],d8['risk'],last)
        result=run_historical_policy(world,settings,suppliers,policy,first,last,store.history_as_of)
        if not result['complete']:raise AssertionError('Synthetic preflight failed: '+name+str(result['failure']))
        if len(result['ledger'])!=24 or len(result['decision_audit'])!=22:raise AssertionError('Holdout-shaped calendar mismatch')
        results[name]=result;plans[name]=getattr(policy,'history',[])
        timing.extend({'policy':name,'origin':origins[i],'status':s.status,'seconds':s.solve_seconds} for i,s in enumerate(getattr(policy,'solutions',[])))
    for model in models:
        assert [r['planning_scenarios'] for r in plans['rn_'+model]]==[r['planning_scenarios'] for r in plans['ra_'+model]]
    bridge=parse_month_label(c['bridge_month'])
    assert bridge not in {p.month for p in store.history_as_of(first)}
    assert bridge in {p.month for p in store.history_as_of(add_months(first,1))}
    return {'results':results,'plans':plans,'fit_audit':fit_audit,'pool_audit':pool_audit,'purpose_checks':purpose_checks,
        'observations':observations,'settings':settings,'suppliers':suppliers,'timing':timing,
        'summary':{'knowledge_type':config['synthetic']['knowledge_type'],'policies':7,'origins_per_policy':22,
            'ledger_months_per_policy':24,'active_months':21,'runoff_months':3,'native_fake_sarimax_calls':22,
            'native_fake_lightgbm_predictors':66,'actual_model_training_calls':0,'actual_price_reads':0,
            'optimal_solves':sum(t['status']=='OPTIMAL' for t in timing),'bridge_asof_passed':True,
            'production_oof_generator_used':False,'fixture_pool_window':60}}
