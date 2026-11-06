"""Immutable native forecast issuance at the live session clock; no truth-reader argument."""

from dataclasses import dataclass,asdict
from datetime import date,datetime
import json
import math
from pathlib import Path

from food_procurement_intelligence.data.sequential import canonical_hash
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.evaluation.splits import ForecastSample,LeakageError,add_months,decision_at,eligible_training_samples
from food_procurement_intelligence.features.price import FeatureSpec
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.uncertainty.contracts import UncertaintyPrediction
from food_procurement_intelligence.uncertainty.models import sarimax_intervals,lightgbm_quantiles
from food_procurement_intelligence.uncertainty.validity import assert_native_raw


def without_timing(value):
    if isinstance(value,dict):return {k:without_timing(v) for k,v in value.items() if not k.endswith('_seconds')}
    if isinstance(value,(list,tuple)):return [without_timing(v) for v in value]
    return value


@dataclass(frozen=True)
class IssuedForecast:
    origin: date
    label: str
    raw: tuple[UncertaintyPrediction,...]
    proof_json: str
    events_json: str
    knowledge_type: str = 'synthetic_day12_not_world_bank'
    backend_kind: str = 'native_statsmodels_lightgbm'

    def __post_init__(self):
        if (self.label not in ('sarimax','lightgbm') or tuple(p.horizon for p in self.raw)!=(1,2,3)
            or len({p.model_name for p in self.raw})!=1 or any(p.forecast_origin!=self.origin
                or p.calibration_status!='raw_not_requested' for p in self.raw)):
            raise ValueError('Complete immutable raw issuance required')
        proof=json.loads(self.proof_json)
        if (proof['forecast_origin']!=self.origin.strftime('%Y-%m')
            or proof['information_cutoff']!=add_months(self.origin,-1).strftime('%Y-%m')
            or proof['training_origin_end']>add_months(self.origin,-4).strftime('%Y-%m')
            or proof['last_complete_training_target']>add_months(self.origin,-1).strftime('%Y-%m')
            or proof['max_training_available_at']>decision_at(self.origin).isoformat()
            or not proof['target_unobserved_at_issue']):raise LeakageError('Invalid issuance training proof')

    def record(self) -> dict:
        return {'origin':self.origin.strftime('%Y-%m'),'label':self.label,'raw':[p.record() for p in self.raw],
            'proof':json.loads(self.proof_json),'events':json.loads(self.events_json),
            'knowledge_type':self.knowledge_type,'backend_kind':self.backend_kind}

    @property
    def digest(self) -> str:return canonical_hash(self.record())

    def points(self) -> tuple[ModelPrediction,...]:
        return tuple(ModelPrediction(p.forecast_origin,p.information_cutoff,p.target_month,p.horizon,
            p.point_prediction,p.model_name) for p in self.raw)


class NativeForecastPublisher:
    def __init__(self,d4: dict,candidates: tuple[ForecastSample,...],directory: Path|None=None):
        self.d4=d4;self.candidates=candidates;self.directory=directory;self._issued={};self.events=[]
        if directory:directory.mkdir(parents=True,exist_ok=True)

    def publish(self,store,origin: date) -> tuple[IssuedForecast,...]:
        if store.clock!=origin or origin in self._issued:raise LeakageError('Issue exactly once at current session origin; no backfill')
        sample=ForecastSample(origin,(1,2,3),tuple(add_months(origin,h) for h in (1,2,3)))
        mature=eligible_training_samples(self.candidates,origin)
        store.assert_training_samples_available(mature,origin)
        history=store.history_as_of(origin)
        if not history or not mature:raise ValueError('Insufficient synthetic native history/labels')
        proof={'forecast_origin':origin.strftime('%Y-%m'),'forecast_asof_at':decision_at(origin).isoformat(),
            'information_cutoff':sample.feature_cutoff.strftime('%Y-%m'),'history_end':max(p.month for p in history).strftime('%Y-%m'),
            'history_sha256':canonical_hash([p.__dict__ for p in history]),'history_n':len(history),
            'training_origin_end':max(s.origin for s in mature).strftime('%Y-%m'),
            'last_complete_training_target':max(m for s in mature for m in s.targets).strftime('%Y-%m'),
            'max_training_available_at':max(p.available_at for p in history if p.month in {m for s in mature for m in s.targets}).isoformat(),
            'source_session':store.permit.session_id,'source_id':store.permit.source_id,
            'training_samples':len(mature),'feature_count':15,'model_steps':[2,3,4],
            'target_unobserved_at_issue':all(m>sample.feature_cutoff for m in sample.targets)}
        batches=[]
        for label in ('sarimax','lightgbm'):
            if label=='sarimax':rows,events=sarimax_intervals(store,sample,self.d4[label])
            else:rows,events=lightgbm_quantiles(store,sample,self.d4[label],FeatureSpec(),self.candidates)
            self.events.extend({'label':label,'origin':origin.strftime('%Y-%m'),**e} for e in events)
            if len(rows)!=3 or any(e['status']!='success' for e in events):
                raise RuntimeError('Native fit failed: '+label+' '+str(origin)+' '+str(without_timing(events)))
            for h,p in enumerate(rows,1):
                if (p.forecast_origin!=origin or p.model_name!=self.d4[label]['model_name'] or p.horizon!=h
                    or p.target_month!=add_months(origin,h) or p.information_cutoff!=sample.feature_cutoff
                    or p.calibration_status!='raw_not_requested'):
                    raise ValueError('Native forecast contract failure; no clipping/fallback')
                assert_native_raw(p)
            model_proof={**proof,'model_spec_sha256':canonical_hash(self.d4[label]),
                'feature_spec_sha256':canonical_hash(asdict(FeatureSpec()))}
            issued=IssuedForecast(origin,label,tuple(rows),json.dumps(model_proof,sort_keys=True),
                json.dumps(_serializable(without_timing(events)),sort_keys=True))
            batches.append(issued)
            if self.directory:
                path=self.directory/f'{origin:%Y-%m}_{label}.json'
                with path.open('x',encoding='utf-8') as f:json.dump({'issued_sha256':issued.digest,**issued.record()},f,sort_keys=True,indent=2)
        self._issued[origin]=tuple(batches)
        return tuple(batches)


def load_issued_forecast(path: Path,expected_issuance_sha256: str) -> IssuedForecast:
    """Reload an externally pinned issuance; never estimate a missing historical forecast."""
    value=json.loads(path.read_text(encoding='utf-8'));digest=value.pop('issued_sha256')
    if digest!=expected_issuance_sha256 or canonical_hash(value)!=digest:raise LeakageError('Stored issuance hash mismatch')
    raw=[]
    month_fields=('forecast_origin','information_cutoff','target_month','fit_information_end','calibration_cutoff')
    stamp_fields=('fit_max_label_available_at','calibration_max_available_at')
    for row in value['raw']:
        fields={k:row[k] for k in UncertaintyPrediction.__dataclass_fields__}
        for k in month_fields:
            if fields[k] is not None:fields[k]=date.fromisoformat(fields[k]+'-01')
        for k in stamp_fields:
            if fields[k] is not None:fields[k]=datetime.fromisoformat(fields[k])
        raw.append(UncertaintyPrediction(**fields))
    batch=IssuedForecast(date.fromisoformat(value['origin']+'-01'),value['label'],tuple(raw),
        json.dumps(value['proof'],sort_keys=True),json.dumps(value['events'],sort_keys=True),value['knowledge_type'],value['backend_kind'])
    if batch.digest!=digest:raise LeakageError('Stored derived issuance fields changed')
    return batch
