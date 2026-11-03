"""Typed Legacy seed restoration with unchanged Day15 numeric lifecycle."""
import json
from food_procurement_intelligence.data.sequential import canonical_hash
from food_procurement_intelligence.evaluation.splits import LeakageError,months_between,parse_month_label
from food_procurement_intelligence.forecasting.legacy import LegacyReconstructedForecast,NativeIssuedForecast
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher
from food_procurement_intelligence.uncertainty.horizon_sequential import HorizonSequentialOOF


class ProvenanceSequentialOOF(HorizonSequentialOOF):
    """Legacy has no proof_json/native session. Dispatch validation by actual type."""
    def __init__(self,*args,legacy_model_specs:dict[str,str],legacy_snapshot:str,**kwargs):
        super().__init__(*args,**kwargs)
        self.legacy_model_specs=dict(legacy_model_specs);self.legacy_snapshot=legacy_snapshot;self.lineage={};self.native_issuer=None

    def bind_native_issuer(self,issuer:NativeForecastPublisher) -> None:
        if type(issuer) is not NativeForecastPublisher or self.native_issuer is not None:
            raise TypeError('Bind the actual native publisher once; no fake/replay issuer')
        self.native_issuer=issuer

    def _assert_session_issuance(self,batch,restored_archive:bool=False):
        if type(batch) is LegacyReconstructedForecast:
            if (batch.source_kind!='synthetic_legacy_fixture' or batch.source_identity!=self.permit.source_id
                or batch.snapshot_identity!=self.legacy_snapshot
                or batch.model_spec_sha256!=self.legacy_model_specs.get(batch.label)
                or any(p.model_name!=self.models[batch.label] for p in batch.raw)):
                raise LeakageError('Legacy/source proof incompatible; actual source runtime remains unauthorized')
            return
        if type(batch) is not NativeIssuedForecast:raise TypeError('Do not convert unknown forecast evidence to Native')
        if restored_archive:raise TypeError('Historical seed enters as Legacy; Native means current-run publication')
        if (self.native_issuer is None or batch not in self.native_issuer._issued.get(batch.origin,())):
            raise LeakageError('Native batch was not published by this execution issuer')
        events=json.loads(batch.events_json)
        if len(events)!=(1 if batch.label=='sarimax' else 12) or any(e.get('status')!='success' for e in events):
            raise LeakageError('Native fit evidence missing/failed; cannot mark NATIVE_ISSUED')
        super()._assert_session_issuance(batch,restored_archive)

    def restore_legacy_archive(self,batches,expected_archive_sha256:str) -> None:
        if self.clock is not None or self.pending or self.issued_hashes:raise LeakageError('Restore before session starts only')
        batches=tuple(batches)
        if any(type(b) is not LegacyReconstructedForecast for b in batches):raise TypeError('Legacy restoration requires Legacy records')
        if canonical_hash([b.record() for b in batches])!=expected_archive_sha256:raise LeakageError('Legacy archive hash mismatch')
        historical=set(months_between(parse_month_label(self.d5['historical_origin_start']),parse_month_label(self.d5['historical_origin_end'])))
        validation=set(months_between(self.plan.validation_origin_start,self.plan.validation_origin_end))
        if (len(batches)!=192 or {b.label for b in batches}!={'sarimax','lightgbm'}
            or any({b.origin for b in batches if b.label==label}!=historical|validation for label in ('sarimax','lightgbm'))):
            raise ValueError('Exact original60+36/model calendar; no missing/duplicate/backfilled origin')
        for b in batches:self._assert_session_issuance(b,restored_archive=True)
        for b in batches:
            model=b.raw[0].model_name;key=model,b.origin;phase='historical_train' if b.origin in historical else 'validation'
            self.pending[key]=b,phase;self.issued_hashes[key]=b.digest;self._queue_calibration(b,phase)
            self.lineage[key]={'evidence_level':'RECONSTRUCTED_ASOF','source_kind':b.source_kind,'digest':b.digest,
                'historical_live_issuance':'NOT_VERIFIED','native_session':None,'original_input_byte_proof':None,'native_history_record_hash':None}
            self.issue_log.append({'model':model,'origin':b.origin,'phase':phase,'archive_sha256':expected_archive_sha256,
                **self.lineage[key]})

    def issue(self,batch,phase:str) -> None:
        if type(batch) is not NativeIssuedForecast:raise TypeError('New origin must have a native issuance, not Legacy backfill')
        super().issue(batch,phase)
        self.lineage[batch.raw[0].model_name,batch.origin]={'evidence_level':'NATIVE_ISSUED','source_kind':batch.knowledge_type,
            'digest':batch.digest,'historical_live_issuance':'NOT_CLAIMED_SYNTHETIC_EXECUTION',
            'native_session':self.permit.session_id,'original_input_byte_proof':None,
            'native_history_record_hash':json.loads(batch.proof_json)['history_sha256']}
