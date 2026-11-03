"""Sealed forecast/scenario capabilities; no evaluation-price dependency."""

from datetime import date
import hashlib
import json

from food_procurement_intelligence.evaluation.splits import add_months, HoldoutLockedError, LeakageError
from food_procurement_intelligence.optimization.order_calendar import calendar_planners
from food_procurement_intelligence.policies.fixed import FixedProcurement
from food_procurement_intelligence.policies.forecast_aware import ForecastAware
from food_procurement_intelligence.policies.risk_aware import RiskAware


def record_hash(value) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


class InputPreparationError(ValueError):
    def __init__(self,origin,label,error):
        self.origin=origin
        super().__init__(f'Input preparation {origin:%Y-%m}/{label}: {type(error).__name__}: {error}')


def checked_inputs(origin,model,label,point_adapters,scenario_adapter):
    try:
        points=point_adapters[label](origin)
        if (tuple(p.horizon for p in points)!=(1,2,3)
                or any(p.forecast_origin!=origin or p.model_name!=model or p.information_cutoff!=add_months(origin,-1)
                       or p.target_month!=add_months(origin,p.horizon) or p.unit!='USD_per_metric_tonne' for p in points)):
            raise LeakageError('Point input origin/model/cutoff/target/unit mismatch')
        bundle=scenario_adapter(origin,model).for_policy(origin)
        if bundle.model!=model:
            raise LeakageError('Scenario forecast model mismatch')
        return points,bundle
    except Exception as error:
        raise InputPreparationError(origin,label,error) from error


class PreparedPolicyInputs:
    def __init__(self, origins: tuple[date,...], models: dict[str,str], point_adapters: dict, scenario_adapter):
        self.origins, self.models = origins, models
        self._points, self._scenarios, self.audit = {}, {}, []
        for origin in origins:
            for label,model in models.items():
                points,bundle=checked_inputs(origin,model,label,point_adapters,scenario_adapter)
                self._points[(label,origin)],self._scenarios[(label,origin)]=points,bundle
                self.audit.append({'origin':origin,'model':model,'label':label,
                    'point_sha256':record_hash([p.record() for p in points]),
                    'planning_sha256':record_hash(bundle.records()),'scenario_count':len(bundle.paths),
                    'purpose':bundle.purpose,'shared_rn_ra_input':True})

    def point(self,label: str,origin: date):
        if origin not in self.origins: raise HoldoutLockedError('Out-of-calendar point request')
        return self._points[(label,origin)]

    def scenario(self,label: str,origin: date):
        if origin not in self.origins: raise HoldoutLockedError('Out-of-calendar scenario request')
        return self._scenarios[(label,origin)]


def make_policy(name: str, inputs: PreparedPolicyInputs, settings, lp: dict, risk: dict, last_decision: date):
    if name=='fixed': return FixedProcurement()
    kind,label=name.split('_',1)
    point_planner,risk_planner=calendar_planners(last_decision)
    if kind=='fa':
        return ForecastAware(lambda origin:inputs.point(label,origin),settings,lp,point_planner)
    if kind not in ('rn','ra'): raise ValueError('Unknown policy kind')
    return RiskAware(lambda origin:inputs.scenario(label,origin),settings,lp,
        {**risk,'risk_weight':0. if kind=='rn' else .5},risk_planner)
