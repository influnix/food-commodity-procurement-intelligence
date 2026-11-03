"""Calendar-only split plans, forecast targets and multi-horizon purge masks."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import tomllib
from typing import Iterable, Mapping, Sequence

from food_procurement_intelligence.data.world_bank import assumed_available_at, month_index


class LeakageError(ValueError):
    """A sample uses information unavailable at its decision timestamp."""


class HoldoutLockedError(PermissionError):
    """Development interfaces cannot reveal final holdout observations."""


def parse_month_label(value: str) -> date:
    parsed = date.fromisoformat(value + "-01")
    if parsed.strftime("%Y-%m") != value:
        raise ValueError(f"Expected canonical YYYY-MM: {value!r}")
    return parsed


def add_months(month: date, offset: int) -> date:
    if month.day != 1:
        raise ValueError("Month labels must use the first calendar day")
    index = month_index(month) + offset
    return date(index // 12, index % 12 + 1, 1)


def months_between(start: date, end: date) -> tuple[date, ...]:
    return tuple(add_months(start, step) for step in range(month_index(end) - month_index(start) + 1))


def decision_at(origin: date) -> datetime:
    if origin.day != 1:
        raise ValueError("Origins are month labels, not arbitrary daily timestamps")
    return datetime(origin.year, origin.month, monthrange(origin.year, origin.month)[1], 23, 59, 59, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SplitPlan:
    name: str
    data_start: date
    data_end: date
    train_target_start: date
    train_target_end: date
    validation_origin_start: date
    validation_origin_end: date
    validation_target_start: date
    validation_target_end: date
    bridge_start: date
    bridge_end: date
    holdout_target_start: date
    holdout_target_end: date
    selection_freeze_origin: date
    definition_boundary: date
    minimum_history_months: int = 120
    minimum_sample_history_months: int = 1
    horizons: tuple[int, ...] = (1, 2, 3)
    holdout_locked: bool = True

    def __post_init__(self) -> None:
        if self.horizons != (1, 2, 3) or self.minimum_history_months < 1 or self.minimum_sample_history_months < 1:
            raise ValueError("Day 2 requires horizons 1/2/3 and a positive history size")
        if not self.holdout_locked:
            raise HoldoutLockedError("Day 2 cannot unlock final holdout")
        if not (
            self.data_start == self.train_target_start <= self.train_target_end
            < self.validation_target_start <= self.validation_target_end
            < self.bridge_start <= self.bridge_end
            < self.holdout_target_start <= self.holdout_target_end == self.data_end
        ):
            raise ValueError("Target partitions must be ordered and nonoverlapping")
        if (
            add_months(self.train_target_end, 1) != self.validation_target_start
            or add_months(self.validation_target_end, 1) != self.bridge_start
            or add_months(self.bridge_end, 1) != self.holdout_target_start
        ):
            raise ValueError("Calendar partitions must cover the data without silent gaps")
        if not self.validation_origin_start <= self.validation_origin_end:
            raise ValueError("Invalid validation origins")
        if (
            add_months(self.validation_origin_start, 1) != self.validation_target_start
            or add_months(self.validation_origin_end, 3) != self.validation_target_end
            or self.selection_freeze_origin != add_months(self.holdout_target_start, -1)
        ):
            raise ValueError("Origins and target boundaries are inconsistent")
        if self.validation_target_end > add_months(self.selection_freeze_origin, -1):
            raise LeakageError("Validation labels would be unpublished at selection freeze")

    def target_partition(self, month: date) -> str:
        for label, start, end in (
            ("train", self.train_target_start, self.train_target_end),
            ("validation", self.validation_target_start, self.validation_target_end),
            ("bridge", self.bridge_start, self.bridge_end),
            ("holdout", self.holdout_target_start, self.holdout_target_end),
        ):
            if start <= month <= end:
                return label
        return "outside"


def load_split_plans(path: Path) -> tuple[SplitPlan, tuple[SplitPlan, ...]]:
    with path.open("rb") as file:
        config = tomllib.load(file)
    if config.get("schema_version") != 1 or config["publication_lag_months"] != 1:
        raise ValueError("Unsupported split schema or price-publication lag")
    plans = []
    for candidate in config["candidates"]:
        dates = {key: parse_month_label(value) for key, value in candidate.items() if key != "name"}
        plans.append(SplitPlan(
            name=candidate["name"], data_start=parse_month_label(config["data_start"]),
            data_end=parse_month_label(config["data_end"]),
            definition_boundary=parse_month_label(config["definition_boundary"]),
            minimum_history_months=config["minimum_history_months"],
            minimum_sample_history_months=config["minimum_sample_history_months"],
            horizons=tuple(config["horizons"]), holdout_locked=config["holdout_locked"], **dates,
        ))
    selected = [plan for plan in plans if plan.name == config["selected_candidate"]]
    if len(selected) != 1 or len({plan.name for plan in plans}) != len(plans):
        raise ValueError("Split candidate names must be unique and select exactly one")
    return selected[0], tuple(plans)


@dataclass(frozen=True)
class ForecastSample:
    origin: date
    horizons: tuple[int, ...]
    targets: tuple[date, ...]

    def __post_init__(self) -> None:
        if not self.horizons or len(self.horizons) != len(self.targets):
            raise ValueError("Each sample requires nonempty horizon/target pairs")
        if len(set(self.horizons)) != len(self.horizons) or any(h not in (1, 2, 3) for h in self.horizons):
            raise ValueError("Invalid or duplicated horizons")
        if any(add_months(self.origin, h) != target for h, target in zip(self.horizons, self.targets)):
            raise ValueError("Target months must equal origin plus business horizon")

    @property
    def feature_cutoff(self) -> date:
        return add_months(self.origin, -1)


def forecast_samples(
    calendar: Sequence[date], origins: Iterable[date], minimum_history_months: int,
    complete_only: bool = True,
) -> tuple[ForecastSample, ...]:
    """Generate date masks only; targets outside the observed calendar are omitted."""
    if len(set(calendar)) != len(calendar) or any(month.day != 1 for month in calendar):
        raise ValueError("Calendar must contain unique month labels")
    if minimum_history_months < 1:
        raise ValueError("minimum_history_months must be positive")
    observed = set(calendar)
    samples = []
    for origin in origins:
        cutoff = add_months(origin, -1)
        if sum(month <= cutoff for month in calendar) < minimum_history_months:
            continue
        pairs = [(h, add_months(origin, h)) for h in (1, 2, 3) if add_months(origin, h) in observed]
        if not pairs or (complete_only and len(pairs) != 3):
            continue
        samples.append(ForecastSample(origin, tuple(h for h, _ in pairs), tuple(month for _, month in pairs)))
    return tuple(samples)


def _availability(month: date, available_at: Mapping[date, datetime] | None) -> datetime:
    stamp = datetime.fromisoformat(assumed_available_at(month)) if available_at is None else available_at[month]
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise LeakageError("Availability timestamps must be timezone-aware")
    return stamp


def eligible_training_samples(
    samples: Iterable[ForecastSample], evaluation_origin: date,
    available_at: Mapping[date, datetime] | None = None,
) -> tuple[ForecastSample, ...]:
    cutoff, stamp = add_months(evaluation_origin, -1), decision_at(evaluation_origin)
    return tuple(
        sample for sample in samples
        if sample.origin < evaluation_origin
        and all(target <= cutoff and _availability(target, available_at) <= stamp for target in sample.targets)
    )


def assert_training_available(
    samples: Sequence[ForecastSample], evaluation_origin: date,
    available_at: Mapping[date, datetime] | None = None,
) -> None:
    if eligible_training_samples(samples, evaluation_origin, available_at) != tuple(samples):
        raise LeakageError("Training sample contains a future/unpublished target")


def assert_no_target_overlap(left: Iterable[ForecastSample], right: Iterable[ForecastSample]) -> None:
    overlap = {target for sample in left for target in sample.targets} & {target for sample in right for target in sample.targets}
    if overlap:
        raise LeakageError(f"Forbidden target overlap: {[month.isoformat() for month in sorted(overlap)]}")


def samples_in_partition(samples: Iterable[ForecastSample], plan: SplitPlan, partition: str) -> tuple[ForecastSample, ...]:
    return tuple(sample for sample in samples if all(plan.target_partition(target) == partition for target in sample.targets))


def sample_metadata(sample: ForecastSample, plan: SplitPlan) -> list[dict[str, str | int | bool]]:
    return [
        {"origin_month": sample.origin.strftime("%Y-%m"), "decision_at": decision_at(sample.origin).isoformat(),
         "feature_cutoff_month": sample.feature_cutoff.strftime("%Y-%m"),
         "horizon": horizon, "target_month": target.strftime("%Y-%m"),
         "steps_from_latest_observation": horizon + 1,
         "evaluation_history_ready": month_index(sample.feature_cutoff) - month_index(plan.data_start) + 1 >= plan.minimum_history_months,
         "target_partition": plan.target_partition(target),
         "crosses_definition_boundary": sample.feature_cutoff < plan.definition_boundary <= target}
        for horizon, target in zip(sample.horizons, sample.targets)
    ]


def summarize_plan(calendar: Sequence[date], plan: SplitPlan) -> dict:
    if min(calendar) != plan.data_start or max(calendar) != plan.data_end:
        raise ValueError("Split plan does not match the pinned data calendar")
    all_origins = months_between(plan.data_start, plan.data_end)
    # The evaluation warmup is not an arbitrary deletion of historical labels.
    complete = forecast_samples(calendar, all_origins, plan.minimum_sample_history_months)
    groups = {label: samples_in_partition(complete, plan, label) for label in ("train", "validation", "holdout")}
    if tuple(sample.origin for sample in groups["validation"]) != months_between(plan.validation_origin_start, plan.validation_origin_end):
        raise ValueError("Validation calendar is incomplete")
    assert_no_target_overlap(groups["train"], groups["validation"])
    assert_no_target_overlap(groups["validation"], groups["holdout"])
    assert_no_target_overlap(groups["train"], groups["holdout"])
    first_origin = plan.validation_origin_start
    if sum(month <= add_months(first_origin, -1) for month in calendar) < plan.minimum_history_months:
        raise ValueError("First validation origin lacks the minimum initial training history")
    initial_train = eligible_training_samples(groups["train"], first_origin)
    holdout_partial = forecast_samples(
        calendar, months_between(plan.selection_freeze_origin, add_months(plan.data_end, -1)),
        plan.minimum_history_months, complete_only=False,
    )
    result = {}
    for label, samples in groups.items():
        result[label] = {
            "calendar_months": sum(plan.target_partition(month) == label for month in calendar),
            "complete_origins": len(samples), "target_pairs": sum(len(sample.targets) for sample in samples),
            "unique_target_months": len({target for sample in samples for target in sample.targets}),
            "first_origin": samples[0].origin.strftime("%Y-%m") if samples else None,
            "last_origin": samples[-1].origin.strftime("%Y-%m") if samples else None,
            "horizon_pair_counts": {str(h): sum(h in sample.horizons for sample in samples) for h in (1, 2, 3)},
        }
    return {
        "candidate": plan.name, "partitions": result,
        "bridge_months": sum(plan.target_partition(month) == "bridge" for month in calendar),
        "initial_validation_fit": {
            "origin": first_origin.strftime("%Y-%m"), "observed_through": add_months(first_origin, -1).strftime("%Y-%m"),
            "available_price_months": sum(month <= add_months(first_origin, -1) for month in calendar),
            "mature_complete_training_origins": len(initial_train),
            "training_target_pairs": sum(len(sample.targets) for sample in initial_train),
            "last_mature_training_origin": initial_train[-1].origin.strftime("%Y-%m") if initial_train else None,
            "unpublished_static_train_origins_purged": len(groups["train"]) - len(initial_train),
        },
        "holdout_partial_horizon_structure_only": {
            "origins": len(holdout_partial),
            "target_pairs": sum(len(sample.targets) for sample in holdout_partial),
            "horizon_pair_counts": {str(h): sum(h in sample.horizons for sample in holdout_partial) for h in (1, 2, 3)},
        },
        "holdout_locked": True,
    }
