"""Session-scoped sequential observations; no file loader and no real capability issuer."""

from contextlib import contextmanager
from dataclasses import dataclass,asdict
from datetime import date,datetime
import builtins
import hashlib
import io
import json
import math
import os
from pathlib import Path
from unittest.mock import patch

from .availability import VisiblePrice,assert_feature_available
from food_procurement_intelligence.evaluation.splits import (
    HoldoutLockedError,LeakageError,add_months,assert_training_available,decision_at,
)


@contextmanager
def integration_source_guard(root: Path):
    """Python-level deny-all data opens except explicitly allowed Day11/12 fixtures."""
    data=(root/'data').resolve();allowed=tuple((root/'data/synthetic'/n).resolve() for n in ('day11','day12'))
    audit={'blocked_attempts':[],'actual_source_opens':0}
    def wrap(original):
        def guarded(file,*args,**kwargs):
            if not isinstance(file,int):
                try:p=Path(os.fsdecode(file)).resolve()
                except (ValueError,TypeError):p=None
                if p is not None and p.is_relative_to(data) and not any(p.is_relative_to(a) for a in allowed):
                    audit['blocked_attempts'].append(p.relative_to(root).as_posix())
                    raise HoldoutLockedError('Day12 prohibits real source access')
            return original(file,*args,**kwargs)
        return guarded
    with patch('builtins.open',wrap(builtins.open)),patch('io.open',wrap(io.open)),patch('os.open',wrap(os.open)):
        yield audit


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Observation:
    observation_month: date
    price: float
    actual_available_at: datetime
    availability_basis: str
    vintage_id: str
    source_id: str
    knowledge_type: str = 'synthetic_day12_not_world_bank'
    unit: str = 'USD_per_metric_tonne'

    def __post_init__(self):
        if (self.observation_month.day!=1 or not math.isfinite(self.price) or self.price<=0
            or self.actual_available_at.tzinfo is None or self.actual_available_at.utcoffset() is None
            or not all((self.availability_basis,self.vintage_id,self.source_id)) or self.unit!='USD_per_metric_tonne'):
            raise ValueError('Invalid observation provenance/unit/value')

    @property
    def digest(self) -> str:return canonical_hash(asdict(self))


@dataclass(frozen=True)
class SessionPermit:
    session_id: str
    source_id: str
    knowledge_type: str = 'synthetic_day12_not_world_bank'
    real_data_authorized: bool = False

    def __post_init__(self):
        if self.real_data_authorized or self.knowledge_type!='synthetic_day12_not_world_bank':
            raise HoldoutLockedError('Real session issuance is disabled; separate authorization required')
        if not self.session_id or not self.source_id:raise ValueError('Explicit synthetic session required')


class SequentialObservationStore:
    """Released records only. Historical as-of queries never advance the release clock."""
    def __init__(self,permit: SessionPermit):
        if type(permit) is not SessionPermit:raise HoldoutLockedError('Session permit required')
        self.permit=permit;self.clock: date|None=None;self._released: dict[date,Observation]={}
        self.release_log: list[dict]=[];self._last_publication=None

    @property
    def calendar(self) -> tuple[date,...]:return tuple(sorted(self._released))

    def advance(self,origin: date) -> None:
        if self.clock is not None and origin<=self.clock:raise LeakageError('Duplicate/backwards session clock')
        decision_at(origin);self.clock=origin

    def publish(self,record: Observation) -> None:
        if (type(record) is not Observation or record.knowledge_type!=self.permit.knowledge_type
            or record.source_id!=self.permit.source_id):raise HoldoutLockedError('Observation outside authorized synthetic session')
        if self.clock is None:raise LeakageError('Advance the clock before publication')
        assert_feature_available((record.observation_month,),self.clock,{record.observation_month:record.actual_available_at})
        order=(record.actual_available_at,record.observation_month)
        if record.observation_month in self._released:raise LeakageError('Duplicate publication/revision forbidden')
        if self._last_publication is not None and order<=self._last_publication:raise LeakageError('Backwards publication order')
        self._released[record.observation_month]=record;self._last_publication=order
        self.release_log.append({'observation_month':record.observation_month,'actual_available_at':record.actual_available_at,
            'released_at_origin':self.clock,'source_id':record.source_id,'vintage_id':record.vintage_id,
            'availability_basis':record.availability_basis,'observation_sha256':record.digest})

    def _check(self,origin: date) -> None:
        if self.clock is None or origin>self.clock:raise LeakageError('Future session origin requested')

    def history_as_of(self,origin: date) -> tuple[VisiblePrice,...]:
        self._check(origin)
        return tuple(VisiblePrice(m,r.price,r.unit,r.actual_available_at) for m,r in sorted(self._released.items())
            if m<=add_months(origin,-1) and r.actual_available_at<=decision_at(origin))

    def feature(self,month: date,origin: date) -> float:
        self._check(origin)
        record=self._released.get(month)
        if record is None:raise LeakageError('Unreleased observation access')
        assert_feature_available((month,),origin,{month:record.actual_available_at})
        return record.price

    def assert_training_samples_available(self,samples,evaluation_origin: date) -> None:
        self._check(evaluation_origin)
        if any(m not in self._released for s in samples for m in s.targets):raise LeakageError('Unreleased training target')
        assert_training_available(samples,evaluation_origin,{m:r.actual_available_at for m,r in self._released.items()})

    def training_targets(self,sample,evaluation_origin: date) -> tuple[float,...]:
        self.assert_training_samples_available((sample,),evaluation_origin)
        return tuple(self.feature(m,evaluation_origin) for m in sample.targets)
