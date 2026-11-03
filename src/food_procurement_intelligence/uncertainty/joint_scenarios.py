"""Empirical joint OOF draws. No quantile-to-distribution conversion or truth reader."""

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
from random import Random
from statistics import fmean

from food_procurement_intelligence.evaluation.splits import (
    add_months, decision_at, parse_month_label, HoldoutLockedError, LeakageError,
)
from food_procurement_intelligence.features.price import checked_history
from food_procurement_intelligence.forecasting.common import ModelPrediction
from .calibration import OOFResidual, assert_residual_available


@dataclass(frozen=True)
class JointResidualVector:
    residuals: tuple[OOFResidual, ...]
    point_predictions: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.residuals) != 3 or tuple(r.residual_horizon for r in self.residuals) != (1, 2, 3):
            raise ValueError("Joint vector requires aligned H1/H2/H3, not three arbitrary residuals")
        if len({(r.source_model, r.source_method, r.residual_forecast_origin) for r in self.residuals}) != 1:
            raise LeakageError("Joint vector mixes origins, models or methods")
        if len(self.point_predictions) != 3 or any(not math.isfinite(p) or p <= 0 for p in self.point_predictions):
            raise ValueError("Positive finite OOF point predictions are required")
        for r, p in zip(self.residuals, self.point_predictions):
            if not math.isclose(r.actual_price - p, r.residual_value, rel_tol=1e-12, abs_tol=1e-10):
                raise ValueError("OOF error does not match its actual and point")

    @property
    def origin(self) -> date:
        return self.residuals[0].residual_forecast_origin

    @property
    def model(self) -> str:
        return self.residuals[0].source_model

    @property
    def errors(self) -> tuple[float, ...]:
        return tuple(r.residual_value for r in self.residuals)

    @property
    def ratios(self) -> tuple[float, ...]:
        return tuple(r.actual_price / p for r, p in zip(self.residuals, self.point_predictions))

    def assert_available(self, origin: date, plan) -> None:
        for residual in self.residuals:
            assert_residual_available(residual, origin, plan)

    def record(self, construction_origin: date) -> dict:
        return {"construction_origin": construction_origin.strftime("%Y-%m"), "source_model": self.model,
                "source_oof_origin": self.origin.strftime("%Y-%m"), "horizons": [1, 2, 3],
                "target_months": [r.residual_target_month.strftime("%Y-%m") for r in self.residuals],
                "actual_available_at": [r.residual_actual_available_at.isoformat() for r in self.residuals],
                "fit_information_end": [r.fit_information_end.strftime("%Y-%m") for r in self.residuals],
                "fit_max_label_available_at": [r.fit_max_label_available_at.isoformat() for r in self.residuals],
                "point_predictions": self.point_predictions, "actual_prices": [r.actual_price for r in self.residuals],
                "errors": self.errors, "ratios": self.ratios, "phase": self.residuals[0].phase,
                "unit": "USD_per_metric_tonne"}


class SavedOOFForecasts:
    """Read-only point/proof view of Day 5 forecasts; there are no actual columns.

    Future point strings stay private. Decode values only for the current forecast
    or a fully mature historical vector. Actuals always come from guarded history.
    """

    def __init__(self, rows: list[dict], plan):
        self.plan = plan
        self._groups: dict[tuple, dict] = {}
        for raw in rows:
            if "actual_price" in raw:
                raise ValueError("Joint forecast source must not contain a validation answer column")
            origin, target = parse_month_label(raw["forecast_origin"]), parse_month_label(raw["target_month"])
            h = int(raw["horizon"])
            if h not in (1, 2, 3) or target != add_months(origin, h):
                raise LeakageError("OOF source target/horizon mismatch")
            partition = plan.target_partition(target)
            if partition not in ("train", "validation"):
                raise HoldoutLockedError("Bridge/holdout OOF source is forbidden")
            if raw["phase"] == "historical_train" and partition != "train":
                raise LeakageError("Historical source escaped Train")
            if raw["phase"] not in ("historical_train", "validation"):
                raise ValueError("Unknown OOF source phase")
            if raw["phase"] == "validation" and (partition != "validation" or not plan.validation_origin_start <= origin <= plan.validation_origin_end):
                raise LeakageError("Validation source escaped its frozen calendar")
            stamp = datetime.fromisoformat(raw["fit_max_label_available_at"])
            if (parse_month_label(raw["fit_information_end"]) > add_months(origin, -1)
                    or stamp.tzinfo is None or stamp.utcoffset() is None or stamp > decision_at(origin)):
                raise LeakageError("OOF source was trained on future/unpublished input")
            if raw["forecast_asof_at"] != decision_at(origin).isoformat() or raw["unit"] != "USD_per_metric_tonne":
                raise ValueError("OOF source clock/unit mismatch")
            if raw.get("information_cutoff", add_months(origin, -1).strftime("%Y-%m")) != add_months(origin, -1).strftime("%Y-%m"):
                raise LeakageError("OOF source cutoff is not t-1")
            group = self._groups.setdefault((raw["model_name"], origin), {})
            if h in group:
                raise ValueError("Duplicate OOF source horizon")
            group[h] = dict(raw)

    def points_at(self, origin: date, model: str) -> tuple[ModelPrediction, ...]:
        if not self.plan.validation_origin_start <= origin <= self.plan.validation_origin_end:
            raise HoldoutLockedError("Only frozen development forecast origins are available")
        group = self._groups.get((model, origin), {})
        if set(group) != {1, 2, 3}:
            raise LookupError("Current three-horizon point forecast is incomplete")
        return tuple(ModelPrediction(origin, add_months(origin, -1), add_months(origin, h), h,
                                     float(group[h]["point_prediction"]), model) for h in (1, 2, 3))

    def vectors_as_of(self, store, origin: date, model: str, window: int):
        if window < 1:
            raise ValueError("Joint pool window must be positive")
        history = checked_history(store.history_as_of(origin), origin)
        vectors, counts = [], {"incomplete": 0, "future_or_immature": 0}
        for (source_model, past), group in sorted(self._groups.items()):
            if source_model != model:
                continue
            if set(group) != {1, 2, 3}:
                counts["incomplete"] += 1
                continue
            targets = tuple(add_months(past, h) for h in (1, 2, 3))
            if (past >= origin or max(targets) > add_months(origin, -1)
                    or any(target not in history or history[target].price is None for target in targets)):
                counts["future_or_immature"] += 1
                continue
            residuals, points = [], []
            for h, target in zip((1, 2, 3), targets):
                raw, actual = group[h], history[target]
                point = float(raw["point_prediction"])
                # Nonconformity score is unused here; this is a point-error vector.
                residuals.append(OOFResidual(past, target, h, actual.available_at, source_model,
                    raw["uncertainty_method"], actual.price - point, 0.0, actual.price,
                    parse_month_label(raw["fit_information_end"]), datetime.fromisoformat(raw["fit_max_label_available_at"]),
                    origin, raw["phase"]))
                points.append(point)
            vector = JointResidualVector(tuple(residuals), tuple(points))
            vector.assert_available(origin, self.plan)
            vectors.append(vector)
        counts["eligible_before_window"] = len(vectors)
        selected = tuple(sorted(vectors, key=lambda v: v.origin)[-window:])
        counts["selected"] = len(selected)
        return selected, counts


def derived_seed(base: int, origin: date, model: str, purpose: str) -> int:
    if purpose not in ("planning", "evaluation") or type(base) is not int or base < 0:
        raise ValueError("Invalid scenario seed/purpose")
    return int.from_bytes(hashlib.sha256(f"{base}|{origin:%Y-%m}|{model}|{purpose}".encode()).digest()[:16], "big")


@dataclass(frozen=True)
class PricePath:
    scenario_id: str
    source_oof_origin: date
    prices: tuple[float, ...]
    weight: float

    def __post_init__(self) -> None:
        if not self.scenario_id or len(self.prices) != 3 or any(not math.isfinite(p) or p <= 0 for p in self.prices):
            raise ValueError("Invalid price path; no clipping or replacement draw")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("Scenario weights must be positive and finite")


@dataclass(frozen=True)
class ScenarioSet:
    origin: date
    model: str
    purpose: str
    method: str
    seed: int
    paths: tuple[PricePath, ...]
    pool_sha256: str

    def __post_init__(self) -> None:
        if self.purpose not in ("planning", "evaluation") or not self.paths:
            raise ValueError("Empty scenario set or invalid purpose")
        if len({p.scenario_id for p in self.paths}) != len(self.paths):
            raise ValueError("Duplicate scenario ID")
        if not math.isclose(math.fsum(p.weight for p in self.paths), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("Scenario probabilities must sum to one")

    def records(self) -> list[dict]:
        return [{"scenario_id": p.scenario_id, "purpose": self.purpose, "forecast_origin": self.origin.strftime("%Y-%m"),
                 "forecast_asof_at": decision_at(self.origin).isoformat(), "information_cutoff": add_months(self.origin, -1).strftime("%Y-%m"),
                 "source_model": self.model, "source_oof_origin": p.source_oof_origin.strftime("%Y-%m"),
                 "target_month": add_months(self.origin, h).strftime("%Y-%m"), "horizon": h,
                 "price": price, "probability": p.weight, "seed": str(self.seed), "method": self.method,
                 "pool_sha256": self.pool_sha256, "unit": "USD_per_metric_tonne", "knowledge_type": "empirical_simulation_not_observed"}
                for p in self.paths for h, price in enumerate(p.prices, 1)]

    def for_policy(self, decision_origin: date):
        """Explicit future consumer boundary: evaluation paths are engine-only."""
        if self.purpose != "planning" or self.origin != decision_origin:
            raise LeakageError("Policy input requires planning paths issued at its own decision origin")
        return self


def moments(vectors) -> dict:
    if not vectors or any(len(v) != 3 or any(not math.isfinite(x) for x in v) for v in vectors):
        raise ValueError("Moment diagnostics require finite 3D rows")
    means = [fmean(v[h] for v in vectors) for h in range(3)]
    cov = [[math.fsum((v[i] - means[i]) * (v[j] - means[j]) for v in vectors) / len(vectors)
            for j in range(3)] for i in range(3)]
    corr = [[cov[i][j] / math.sqrt(cov[i][i] * cov[j][j]) if cov[i][i] > 0 and cov[j][j] > 0 else None
             for j in range(3)] for i in range(3)]
    return {"n": len(vectors), "mean": means, "variance": [cov[i][i] for i in range(3)],
            "covariance": cov, "correlation": corr, "variance_basis": "empirical_population_divisor_n"}


def generate_joint_scenarios(vectors, points, origin, model, purpose, config, plan, rng: Random, seed: int):
    if (not plan.validation_origin_start <= origin <= plan.validation_origin_end
            or any(plan.target_partition(p.target_month) != "validation" for p in points)):
        raise HoldoutLockedError("Day 6 scenario generation is restricted to frozen development keys")
    if purpose not in ("planning", "evaluation") or len(vectors) < config["minimum_joint_vectors"]:
        raise ValueError("Invalid purpose or insufficient complete OOF vectors; no fallback")
    if config["method"] != "multiplicative_joint_oof" or config["fallback"] != "fail_no_clipping_no_resampling":
        raise ValueError("Unsupported Day 6 scenario specification")
    if type(config["scenario_count"]) is not int or config["scenario_count"] < 1:
        raise ValueError("Positive integer scenario count required")
    if rng.getstate() != Random(seed).getstate():
        raise ValueError("Pass a fresh isolated RNG matching the declared seed")
    if (tuple(p.horizon for p in points) != (1, 2, 3)
            or any(p.forecast_origin != origin or p.model_name != model for p in points)):
        raise ValueError("Scenario points must share the current model/origin and all horizons")
    for vector in vectors:
        if vector.model != model:
            raise LeakageError("Joint pool mixes source models")
        vector.assert_available(origin, plan)
    if len({v.origin for v in vectors}) != len(vectors):
        raise ValueError("Duplicate joint OOF origin")
    pool_hash = hashlib.sha256(json.dumps([v.record(origin) for v in vectors], sort_keys=True).encode()).hexdigest()
    paths, additive, sampled_ratios = [], [], []
    for index in range(config["scenario_count"]):
        vector = vectors[rng.randrange(len(vectors))]
        values = tuple(p.predicted_price * ratio for p, ratio in zip(points, vector.ratios))
        identifier = f"{purpose}|{model}|{origin:%Y-%m}|{index:04d}"
        paths.append(PricePath(identifier, vector.origin, values, 1 / config["scenario_count"]))
        additive.append(tuple(p.predicted_price + error for p, error in zip(points, vector.errors)))
        sampled_ratios.append(vector.ratios)
    bundle = ScenarioSet(origin, model, purpose, config["method"], seed, tuple(paths), pool_hash)
    invalid_additive = sum(any(not math.isfinite(p) or p <= 0 for p in row) for row in additive)
    diagnostics = {"origin": origin.strftime("%Y-%m"), "model": model, "purpose": purpose,
        "pool_n": len(vectors), "scenario_count": len(paths), "probability_sum": math.fsum(p.weight for p in paths),
        "pool_error_moments": moments([v.errors for v in vectors]), "pool_ratio_moments": moments([v.ratios for v in vectors]),
        "sampled_ratio_moments": moments(sampled_ratios), "price_moments": moments([p.prices for p in paths]),
        "minimum_price": min(x for p in paths for x in p.prices), "invalid_price_paths": 0,
        "additive_same_draw_invalid_paths": invalid_additive,
        "additive_same_draw_moments": moments(additive) if all(math.isfinite(x) for v in additive for x in v) else None,
        "distinct_sampled_origins": len({p.source_oof_origin for p in paths}), "pool_sha256": pool_hash,
        "interpretation": "empirical joint draws; no 80% coverage or independent/OOS market-distribution claim"}
    return bundle, diagnostics
