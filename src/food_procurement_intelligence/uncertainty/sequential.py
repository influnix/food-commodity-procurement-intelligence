"""New-session OOF lifecycle. Legacy validation-only guards are untouched."""

from dataclasses import replace
from datetime import date
import json
from random import Random

from food_procurement_intelligence.data.sequential import canonical_hash
from food_procurement_intelligence.evaluation.splits import LeakageError,add_months,decision_at,months_between,parse_month_label
from food_procurement_intelligence.uncertainty.calibration import finite_sample_adjustment
from food_procurement_intelligence.uncertainty.joint_scenarios import PricePath,ScenarioSet,derived_seed


class SequentialOOF:
    def __init__(self,permit,d5: dict,scenario_config: dict,plan):
        self.permit=permit;self.d5=d5;self.config=scenario_config;self.plan=plan
        self.clock=None;self.pending={};self.released={};self.issued_hashes={};self.issue_log=[]

    def _assert_session_issuance(self,issued,restored_archive: bool=False) -> None:
        proof=json.loads(issued.proof_json)
        if (issued.knowledge_type!=self.permit.knowledge_type or issued.backend_kind!='native_statsmodels_lightgbm'
            or proof['source_id']!=self.permit.source_id
            or not restored_archive and proof['source_session']!=self.permit.session_id):
            raise LeakageError('Forecast batch is outside the authorized source/backend session')

    def restore_seed_archive(self,batches,expected_archive_sha256: str) -> None:
        """Restore already issued, externally pinned records; never fit/backfill a seed."""
        if self.clock is not None or self.pending or self.released:raise LeakageError('Seed restore only before session begins')
        if canonical_hash([b.record() for b in batches])!=expected_archive_sha256:raise LeakageError('Seed archive hash mismatch')
        historical=set(months_between(parse_month_label(self.d5['historical_origin_start']),parse_month_label(self.d5['historical_origin_end'])))
        validation=set(months_between(self.plan.validation_origin_start,self.plan.validation_origin_end))
        labels={b.label for b in batches}
        if labels!={'sarimax','lightgbm'} or len(batches)!=192 or any({b.origin for b in batches if b.label==label}!=historical|validation for label in labels):
            raise ValueError('Seed must retain original60+36 origins per model; no gap backfill')
        for b in batches:
            self._assert_session_issuance(b,restored_archive=True)
            if b.knowledge_type!=self.permit.knowledge_type or json.loads(b.proof_json)['source_id']!=self.permit.source_id:
                raise LeakageError('Seed source/knowledge type mismatch')
            key=b.raw[0].model_name,b.origin
            if key in self.pending:raise LeakageError('Duplicate seed')
            phase='historical_train' if b.origin in historical else 'validation'
            self.pending[key]=b,phase;self.issued_hashes[key]=b.digest
            self.issue_log.append({'model':key[0],'origin':b.origin,'phase':phase,'issued_sha256':b.digest,
                'restored_pinned_issuance':True,'archive_sha256':expected_archive_sha256,'knowledge_type':b.knowledge_type})

    def tick(self,store,origin: date) -> None:
        if store.permit!=self.permit or store.clock!=origin or self.clock is not None and origin<=self.clock:
            raise LeakageError('OOF clock/session mismatch')
        history={p.month:p for p in store.history_as_of(origin)}
        for key,(issued,phase) in list(self.pending.items()):
            if issued.digest!=self.issued_hashes[key]:raise LeakageError('Issued forecast changed')
            if add_months(issued.origin,3)>add_months(origin,-1) or any(p.target_month not in history for p in issued.raw):continue
            actual=[history[p.target_month] for p in issued.raw]
            if any(a.available_at>decision_at(origin) for a in actual):raise LeakageError('Unpublished vector release')
            vector={'model':issued.raw[0].model_name,'source_origin':issued.origin,'phase':phase,
                'issuance_sha256':issued.digest,'targets':tuple(p.target_month for p in issued.raw),
                'actual_available_at':tuple(a.available_at for a in actual),'actual_prices':tuple(a.price for a in actual),
                'points':tuple(p.point_prediction for p in issued.raw),
                'ratios':tuple(a.price/p.point_prediction for a,p in zip(actual,issued.raw)),
                'scores':tuple(max(p.lower_bound-a.price,a.price-p.upper_bound,0.) if p.interval_usable else None for a,p in zip(actual,issued.raw)),
                'raw_methods':tuple(p.uncertainty_method for p in issued.raw),'fit_information_end':tuple(p.fit_information_end for p in issued.raw),
                'fit_max_label_available_at':tuple(p.fit_max_label_available_at for p in issued.raw),
                'first_released_at_origin':origin,'knowledge_type':issued.knowledge_type}
            self.released[key]=vector;del self.pending[key]
        self.clock=origin

    def issue(self,issued,phase: str) -> None:
        self._assert_session_issuance(issued)
        if (self.clock!=issued.origin or issued.knowledge_type!=self.permit.knowledge_type
            or phase not in ('historical_train','validation','sequential_synthetic')):
            raise LeakageError('No retrospective issuance or unsupported phase/session')
        if issued.backend_kind!='native_statsmodels_lightgbm':raise ValueError('Native issuance required')
        if tuple(p.horizon for p in issued.raw)!=(1,2,3):raise ValueError('Complete OOF issuance required')
        model=issued.raw[0].model_name;key=model,issued.origin
        if phase=='historical_train' and any(self.plan.target_partition(p.target_month)!='train' for p in issued.raw):
            raise LeakageError('Historical seed escaped Train')
        if phase=='validation' and not self.plan.validation_origin_start<=issued.origin<=self.plan.validation_origin_end:
            raise LeakageError('Validation seed origin mismatch')
        if phase=='sequential_synthetic' and not self.plan.selection_freeze_origin<=issued.origin<=add_months(self.plan.holdout_target_end,-3):
            raise LeakageError('New phase outside final calendar')
        if key in self.issued_hashes:raise LeakageError('Duplicate OOF issuance')
        proof=json.loads(issued.proof_json)
        if not proof['target_unobserved_at_issue'] or proof['source_id']!=self.permit.source_id:raise LeakageError('Missing OOF fit/source proof')
        self.issued_hashes[key]=issued.digest;self.pending[key]=issued,phase
        self.issue_log.append({'model':model,'origin':issued.origin,'phase':phase,'issued_sha256':issued.digest,
            'target_unobserved_at_issue':True,'knowledge_type':issued.knowledge_type})

    def _eligible(self,model: str,origin: date) -> list[dict]:
        if origin!=self.clock:raise LeakageError('Pool query outside live OOF clock')
        rows=[v for (m,_),v in self.released.items() if m==model]
        for v in rows:
            if (max(v['targets'])>add_months(origin,-1) or max(v['actual_available_at'])>decision_at(origin)
                or v['first_released_at_origin']>origin or self.issued_hashes.get((model,v['source_origin']))!=v['issuance_sha256']
                or tuple(v['targets'])!=tuple(add_months(v['source_origin'],h) for h in (1,2,3))
                or max(v['fit_information_end'])>add_months(v['source_origin'],-1)
                or max(v['fit_max_label_available_at'])>decision_at(v['source_origin'])):raise LeakageError('Polluted OOF pool')
        return rows

    def vectors(self,model: str,origin: date) -> tuple[dict,...]:
        rows=self._eligible(model,origin)
        return tuple(sorted(rows,key=lambda v:v['source_origin'])[-self.config['pool_window']:])

    def calibrate(self,issued) -> tuple[tuple,...]:
        self._assert_session_issuance(issued)
        origin=issued.origin;model=issued.raw[0].model_name
        if origin!=self.clock:raise LeakageError('Calibration clock mismatch')
        eligible=self._eligible(model,origin)
        outputs=[];audit=[]
        for i,p in enumerate(issued.raw):
            selected=sorted((v for v in eligible if v['scores'][i] is not None),key=lambda v:v['targets'][i])[-self.d5['calibration_window']:]
            if any(v['raw_methods'][i]!=p.uncertainty_method for v in selected):raise ValueError('Calibration method mismatch')
            adjustment,rank=finite_sample_adjustment([v['scores'][i] for v in selected],.8,self.d5['minimum_calibration_samples'])
            status='calibrated' if adjustment is not None else 'insufficient_raw_fallback'
            if not p.interval_usable:status='raw_invalid_uncalibrated';adjustment=None
            low=p.lower_bound-adjustment if adjustment is not None else p.lower_bound
            high=p.upper_bound+adjustment if adjustment is not None else p.upper_bound
            result=replace(p,uncertainty_method=p.uncertainty_method+'_rolling_conformal',q10=None,q50=None,q90=None,
                base_q10=p.q10,base_q50=p.q50,base_q90=p.q90,lower_bound=low if p.interval_usable else None,
                upper_bound=high if p.interval_usable else None,calibration_status=status,calibration_adjustment=adjustment,
                calibration_sample_size=len(selected),calibration_cutoff=max((v['targets'][i] for v in selected),default=None),
                calibration_max_available_at=max((v['actual_available_at'][i] for v in selected),default=None))
            outputs.append(result);audit.append({'origin':origin,'model':model,'horizon':i+1,'status':status,'count':len(selected),
                'rank':rank,'adjustment':adjustment,'selected_issuances':[v['issuance_sha256'] for v in selected],
                'selected_source_origins':[v['source_origin'] for v in selected]})
        return tuple(outputs),tuple(audit)

    def scenarios(self,issued,purpose: str):
        self._assert_session_issuance(issued)
        if purpose not in ('planning','evaluation'):raise ValueError('Unknown scenario purpose')
        origin=issued.origin;model=issued.raw[0].model_name;vectors=self.vectors(model,origin)
        c=self.config
        if c['method']!='multiplicative_joint_oof' or c['scenario_count']!=128 or len(vectors)<c['minimum_joint_vectors']:
            raise ValueError('Insufficient/unsupported joint pool; no fallback')
        seed=derived_seed(c[purpose+'_seed'],origin,model,purpose);rng=Random(seed);paths=[]
        for i in range(c['scenario_count']):
            v=vectors[rng.randrange(len(vectors))]
            values=tuple(p.point_prediction*ratio for p,ratio in zip(issued.raw,v['ratios']))
            paths.append(PricePath(f'{purpose}|{model}|{origin:%Y-%m}|{i:04d}',v['source_origin'],values,1/c['scenario_count']))
        return ScenarioSet(origin,model,purpose,c['method'],seed,tuple(paths),canonical_hash(vectors)),vectors
