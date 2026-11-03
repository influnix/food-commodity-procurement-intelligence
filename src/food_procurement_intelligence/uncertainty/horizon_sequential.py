"""Day15: independent per-horizon Calibration and complete-vector Joint lifecycles."""
from dataclasses import replace
from datetime import date, datetime
import json

from food_procurement_intelligence.evaluation.splits import LeakageError, add_months, decision_at, parse_month_label
from .calibration import finite_sample_adjustment
from .sequential import SequentialOOF
from .validity import validate_forecast


class HorizonSequentialOOF(SequentialOOF):
    """Reuse unchanged Joint ratios/draws; only Calibration releases per horizon."""

    def __init__(self, permit, d5: dict, scenario_config: dict, plan, models: dict[str,str]):
        super().__init__(permit,d5,scenario_config,plan)
        if set(models) != {'sarimax','lightgbm'} or len(set(models.values())) != 2:
            raise ValueError('Two distinct frozen model identities required')
        self.models = dict(models)
        self.calibration_pending = {}
        self.calibration_released = {}

    def _assert_session_issuance(self, issued, restored_archive: bool = False) -> None:
        super()._assert_session_issuance(issued,restored_archive)
        proof = json.loads(issued.proof_json)
        stamp = datetime.fromisoformat(proof['max_training_available_at'])
        if (issued.label not in self.models or any(p.model_name != self.models[issued.label]
            or p.forecast_origin != issued.origin or p.horizon != i
            or p.target_month != add_months(issued.origin,i) or p.calibration_status != 'raw_not_requested'
            or p.fit_information_end > add_months(issued.origin,-1)
            or p.fit_max_label_available_at > decision_at(issued.origin)
            or not validate_forecast(p).point_valid for i,p in enumerate(issued.raw,1))):
            raise LeakageError('Invalid frozen model/horizon/fit/point issuance')
        if (not proof['target_unobserved_at_issue']
            or proof['forecast_origin'] != issued.origin.strftime('%Y-%m')
            or proof['information_cutoff'] != add_months(issued.origin,-1).strftime('%Y-%m')
            or proof['training_origin_end'] > add_months(issued.origin,-4).strftime('%Y-%m')
            or proof['last_complete_training_target'] > add_months(issued.origin,-1).strftime('%Y-%m')
            or stamp.tzinfo is None or stamp.utcoffset() is None or stamp > decision_at(issued.origin)
            or not isinstance(proof.get('source_session'),str) or not proof['source_session']):
            raise LeakageError('Invalid original OOF issuance/fit proof')

    def _queue_calibration(self, issued, phase: str) -> None:
        for p in issued.raw:
            key = p.model_name,issued.origin,p.horizon
            if key in self.calibration_pending or key in self.calibration_released:
                raise LeakageError('Duplicate calibration issuance')
            self.calibration_pending[key] = issued,phase,p

    def issue(self, issued, phase: str) -> None:
        super().issue(issued,phase)
        self._queue_calibration(issued,phase)

    def restore_seed_archive(self, batches, expected_archive_sha256: str) -> None:
        # Validate every batch before mutating either lifecycle (atomic rejection).
        batches = tuple(batches)
        for b in batches:
            self._assert_session_issuance(b,restored_archive=True)
            proof=json.loads(b.proof_json)
            if (proof.get('forecast_asof_at') != decision_at(b.origin).isoformat()
                or not all(proof.get(k) for k in ('history_sha256','model_spec_sha256','feature_spec_sha256'))
                or parse_month_label(proof['history_end']) > add_months(b.origin,-1)):
                raise LeakageError('Archive lacks original native issuance/history/model proof')
        super().restore_seed_archive(batches,expected_archive_sha256)
        for b in batches:
            self._queue_calibration(b,self.pending[(b.raw[0].model_name,b.origin)][1])

    def tick(self, store, origin: date) -> None:
        # Parent verifies full-vector maturity and preserves original ratios/hash/draws.
        super().tick(store,origin)
        history = {p.month:p for p in store.history_as_of(origin)}
        for key,(issued,phase,p) in list(self.calibration_pending.items()):
            if issued.digest != self.issued_hashes[(p.model_name,issued.origin)]:
                raise LeakageError('Calibration issuance mutated')
            actual = history.get(p.target_month)
            if issued.origin >= origin or p.target_month > add_months(origin,-1) or actual is None:
                continue
            if actual.available_at > decision_at(origin):
                raise LeakageError('Calibration actual is unpublished')
            if p.interval_usable:
                self.calibration_released[key] = {'model':p.model_name,'source_origin':issued.origin,'horizon':p.horizon,
                    'target':p.target_month,'actual_available_at':actual.available_at,'phase':phase,
                    'score':max(p.lower_bound-actual.price,actual.price-p.upper_bound,0.),
                    'raw_method':p.uncertainty_method,'issuance_sha256':issued.digest,
                    'fit_information_end':p.fit_information_end,'fit_max_label_available_at':p.fit_max_label_available_at,
                    'first_released_at_origin':origin}
            del self.calibration_pending[key]

    def calibration_residuals(self, model: str, origin: date, horizon: int) -> tuple[dict,...]:
        if origin != self.clock or horizon not in (1,2,3):
            raise LeakageError('Calibration query outside current clock/horizon')
        rows=[]
        for (m,o,h),r in self.calibration_released.items():
            if (r['model'],r['source_origin'],r['horizon']) != (m,o,h):
                raise LeakageError('Polluted calibration identity')
            if (o >= origin or r['target'] != add_months(o,h) or r['target'] > add_months(origin,-1)
                or r['actual_available_at'] > decision_at(origin) or r['first_released_at_origin'] > origin
                or r['fit_information_end'] > add_months(o,-1) or r['fit_max_label_available_at'] > decision_at(o)
                or self.issued_hashes.get((m,o)) != r['issuance_sha256']):
                raise LeakageError('Unissued/future/unpublished calibration residual')
            if (m,h)==(model,horizon):rows.append(r)
        return tuple(sorted(rows,key=lambda r:(r['target'],r['source_origin']))[-self.d5['calibration_window']:])

    def calibrate(self, issued) -> tuple[tuple,...]:
        self._assert_session_issuance(issued)
        if issued.origin != self.clock:raise LeakageError('Calibration clock mismatch')
        outputs=[];audits=[]
        for p in issued.raw:
            selected=self.calibration_residuals(p.model_name,issued.origin,p.horizon)
            if any(r['raw_method']!=p.uncertainty_method for r in selected):
                raise ValueError('Calibration method mismatch')
            adjustment,rank=finite_sample_adjustment([r['score'] for r in selected],p.nominal_coverage,self.d5['minimum_calibration_samples'])
            status='calibrated' if adjustment is not None else 'insufficient_raw_fallback'
            if not p.interval_usable:status='raw_invalid_uncalibrated';adjustment=None
            outputs.append(replace(p,uncertainty_method=p.uncertainty_method+'_rolling_conformal',
                q10=None,q50=None,q90=None,base_q10=p.q10,base_q50=p.q50,base_q90=p.q90,
                lower_bound=p.lower_bound-adjustment if adjustment is not None else p.lower_bound if p.interval_usable else None,
                upper_bound=p.upper_bound+adjustment if adjustment is not None else p.upper_bound if p.interval_usable else None,
                calibration_sample_size=len(selected),calibration_adjustment=adjustment,calibration_status=status,
                calibration_cutoff=max((r['target'] for r in selected),default=None),
                calibration_max_available_at=max((r['actual_available_at'] for r in selected),default=None)))
            audits.append({'origin':issued.origin,'model':p.model_name,'horizon':p.horizon,'status':status,'count':len(selected),
                'rank':rank,'adjustment':adjustment,'selected_issuances':[r['issuance_sha256'] for r in selected],
                'selected_source_origins':[r['source_origin'] for r in selected],'selected_scores':[r['score'] for r in selected]})
        return tuple(outputs),tuple(audits)
