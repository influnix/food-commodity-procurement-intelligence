"""Separate immutable reconstructed forecasts from native IssuedForecast records."""
from dataclasses import dataclass
from datetime import date,datetime
import json

from food_procurement_intelligence.data.sequential import canonical_hash
from food_procurement_intelligence.evaluation.splits import add_months,decision_at,LeakageError,parse_month_label,months_between
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.forecasting.publisher import IssuedForecast as NativeIssuedForecast
from food_procurement_intelligence.uncertainty.contracts import UncertaintyPrediction
from food_procurement_intelligence.uncertainty.validity import validate_forecast


@dataclass(frozen=True)
class LegacyReconstructedForecast:
    origin: date
    label: str
    raw: tuple[UncertaintyPrediction,...]
    original_record_ids: tuple[str,...]
    original_row_hashes: tuple[str,...]
    source_file_sha256: str
    manifest_sha256: str
    model_spec_sha256: str
    snapshot_identity: str
    source_identity: str
    source_kind: str
    source_file_path: str
    manifest_path: str
    knowledge_type: str = 'RECONSTRUCTED_ASOF'
    historical_issuance_evidence_level: str = 'NOT_VERIFIED'

    def __post_init__(self):
        if (self.label not in ('sarimax','lightgbm') or self.knowledge_type!='RECONSTRUCTED_ASOF'
            or self.historical_issuance_evidence_level!='NOT_VERIFIED'
            or self.source_kind not in ('synthetic_legacy_fixture','world_bank_saved_reconstructed')
            or tuple(p.horizon for p in self.raw)!=(1,2,3) or len({p.model_name for p in self.raw})!=1
            or len(self.original_record_ids)!=3 or len(self.original_row_hashes)!=3
            or len(set(self.original_record_ids))!=3):raise ValueError('Invalid reconstructed evidence type/calendar')
        for value in (*self.original_row_hashes,self.source_file_sha256,self.manifest_sha256,self.model_spec_sha256):
            if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Externally pinned SHA required')
        if not self.snapshot_identity or not self.source_identity:raise ValueError('Explicit snapshot/source identity required')
        if any(not p.startswith('artifacts/') or '..' in p.split('/') for p in (self.source_file_path,self.manifest_path)):
            raise ValueError('Legacy must reference pinned saved artifacts, never a raw source loader')
        for p,rid in zip(self.raw,self.original_record_ids):
            if (p.forecast_origin!=self.origin or p.target_month!=add_months(self.origin,p.horizon)
                or p.information_cutoff!=add_months(self.origin,-1) or p.calibration_status!='raw_not_requested'
                or p.fit_information_end>add_months(self.origin,-1) or p.fit_max_label_available_at>decision_at(self.origin)
                or not validate_forecast(p).point_valid or rid!=p.record()['record_id']):
                raise LeakageError('Reconstructed forecast identity/point/as-of/fit proof mismatch')

    def record(self) -> dict:
        return {'origin':f'{self.origin:%Y-%m}','label':self.label,'raw':[p.record() for p in self.raw],
            'original_record_ids':list(self.original_record_ids),'original_row_hashes':list(self.original_row_hashes),
            'source_file_sha256':self.source_file_sha256,'manifest_sha256':self.manifest_sha256,
            'model_spec_sha256':self.model_spec_sha256,'snapshot_identity':self.snapshot_identity,
            'source_identity':self.source_identity,'source_kind':self.source_kind,'knowledge_type':self.knowledge_type,
            'source_file_path':self.source_file_path,'manifest_path':self.manifest_path,
            'historical_issuance_evidence_level':self.historical_issuance_evidence_level,
            'native_session_proof':None,'original_input_byte_proof':None}

    @property
    def digest(self) -> str:return canonical_hash(self.record())

    def points(self) -> tuple[ModelPrediction,...]:return planning_points(self)


def planning_points(batch:LegacyReconstructedForecast|NativeIssuedForecast) -> tuple[ModelPrediction,...]:
    """Common numeric Planning view; returns no promoted or fabricated provenance."""
    if type(batch) not in (LegacyReconstructedForecast,NativeIssuedForecast):raise TypeError('Explicit Legacy or Native forecast type required')
    if tuple(p.horizon for p in batch.raw)!=(1,2,3) or any(not validate_forecast(p).point_valid for p in batch.raw):
        raise ValueError('Planning requires all positive finite point horizons')
    return tuple(ModelPrediction(p.forecast_origin,p.information_cutoff,p.target_month,p.horizon,p.point_prediction,p.model_name) for p in batch.raw)


def legacy_from_saved_rows(rows,*,source_file_sha256:str,manifest_sha256:str,model_specs:dict[str,str],models:dict[str,str],
                           snapshot_identity:str,source_identity:str,source_kind:str,source_file_path:str,manifest_path:str) -> tuple[LegacyReconstructedForecast,...]:
    """Parse already authorized saved forecast rows; no price loader, fit, or native proof synthesis."""
    groups={};names={name:label for label,name in models.items()}
    month_fields=('forecast_origin','information_cutoff','target_month','fit_information_end','calibration_cutoff')
    stamp_fields=('fit_max_label_available_at','calibration_max_available_at')
    numeric={'point_prediction','q10','q50','q90','lower_bound','upper_bound','nominal_coverage','calibration_adjustment','base_q10','base_q50','base_q90'}
    for r in rows:
        if 'actual_price' in r or r['model_name'] not in names:raise ValueError('Forecast input mixes truth or models')
        fields={k:r[k] for k in UncertaintyPrediction.__dataclass_fields__}
        for k in month_fields:fields[k]=parse_month_label(fields[k]) if fields[k] else None
        for k in stamp_fields:fields[k]=datetime.fromisoformat(fields[k]) if fields[k] else None
        for k in numeric:fields[k]=float(fields[k]) if fields[k] not in ('',None) else None
        fields['horizon']=int(fields['horizon']);fields['calibration_sample_size']=int(fields['calibration_sample_size'])
        p=UncertaintyPrediction(**fields);key=p.model_name,p.forecast_origin;group=groups.setdefault(key,{})
        if p.horizon in group:raise ValueError('Duplicate legacy horizon')
        if r['forecast_asof_at']!=decision_at(p.forecast_origin).isoformat():raise LeakageError('Legacy logical issuance timestamp mismatch')
        group[p.horizon]=(p,r['record_id'],canonical_hash(r))
    batches=[]
    for (model,o),group in sorted(groups.items()):
        if set(group)!={1,2,3}:raise ValueError('Incomplete Legacy batch')
        label=names[model]
        batches.append(LegacyReconstructedForecast(o,label,tuple(group[h][0] for h in (1,2,3)),
            tuple(group[h][1] for h in (1,2,3)),tuple(group[h][2] for h in (1,2,3)),
            source_file_sha256,manifest_sha256,model_specs[label],snapshot_identity,source_identity,source_kind,source_file_path,manifest_path))
    return tuple(batches)


def validate_legacy_archive(batches,d5,plan,models,expected_sha256:str) -> dict:
    batches=tuple(batches)
    if any(type(b) is not LegacyReconstructedForecast for b in batches):raise TypeError('Only reconstructed Legacy records')
    if canonical_hash([b.record() for b in batches])!=expected_sha256:raise LeakageError('Legacy archive changed')
    origins=set(months_between(parse_month_label(d5['historical_origin_start']),parse_month_label(d5['historical_origin_end'])))|set(months_between(plan.validation_origin_start,plan.validation_origin_end))
    if (len(batches)!=192 or {b.label for b in batches}!={'sarimax','lightgbm'}
        or any({b.origin for b in batches if b.label==label}!=origins for label in models)
        or any(b.raw[0].model_name!=models[b.label] for b in batches)):
        raise ValueError('Legacy must retain exact Historical60+Validation36/model, no missing/duplicate/backfill')
    for b in batches:
        for p in b.raw:
            if plan.target_partition(p.target_month) not in ('train','validation'):raise LeakageError('Legacy target escaped development scope')
    return {'status':'PASS_RECONSTRUCTED_CONTRACT','batches':192,'horizon_records':576,'knowledge_type':'RECONSTRUCTED_ASOF',
        'historical_live_issuance':'NOT_VERIFIED','native_envelope_fabricated':False}


def legacy_from_records(records,expected_archive_sha256:str) -> tuple[LegacyReconstructedForecast,...]:
    """Reload already supplied/pinned Legacy records without promoting evidence."""
    if canonical_hash(records)!=expected_archive_sha256:raise LeakageError('Legacy serialized archive hash mismatch')
    result=[]
    for r in records:
        if r.get('native_session_proof') is not None or r.get('original_input_byte_proof') is not None:
            raise LeakageError('Legacy archive must not manufacture native input/session proof')
        raw=[]
        for record in r['raw']:
            values={k:record[k] for k in UncertaintyPrediction.__dataclass_fields__}
            for key in ('forecast_origin','information_cutoff','target_month','fit_information_end','calibration_cutoff'):
                if values[key] is not None:values[key]=parse_month_label(values[key])
            for key in ('fit_max_label_available_at','calibration_max_available_at'):
                if values[key] is not None:values[key]=datetime.fromisoformat(values[key])
            raw.append(UncertaintyPrediction(**values))
        b=LegacyReconstructedForecast(parse_month_label(r['origin']),r['label'],tuple(raw),tuple(r['original_record_ids']),
            tuple(r['original_row_hashes']),r['source_file_sha256'],r['manifest_sha256'],r['model_spec_sha256'],
            r['snapshot_identity'],r['source_identity'],r['source_kind'],r['source_file_path'],r['manifest_path'],
            r['knowledge_type'],r['historical_issuance_evidence_level'])
        if b.record()!=r:raise LeakageError('Legacy reload altered or ignored original fields')
        result.append(b)
    return tuple(result)
