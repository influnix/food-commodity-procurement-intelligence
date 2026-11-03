"""Validation-only rolling-origin Seasonal Naive experiment and reproducible CLI."""

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tomllib

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.data.availability import DevelopmentPriceStore
from food_procurement_intelligence.evaluation.forecast_metrics import seasonal_scale, summarize_metrics
from food_procurement_intelligence.evaluation.splits import (
    SplitPlan, assert_no_target_overlap, decision_at, eligible_training_samples,
    forecast_samples, load_split_plans, months_between,
)
from food_procurement_intelligence.features.price import FeatureSpec, FeatureUnavailableError, FeatureVector, build_features
from food_procurement_intelligence.forecasting.seasonal_naive import ForecastUnavailableError, Prediction, predict


@dataclass(frozen=True)
class ValidationResult:
    rows: tuple[dict, ...]
    feature_vectors: tuple[FeatureVector, ...]
    folds: tuple[dict, ...]
    failures: tuple[dict, ...]
    metrics: dict


def run_validation(store: DevelopmentPriceStore, plan: SplitPlan, spec: FeatureSpec) -> ValidationResult:
    """Make ALL predictions before accessing future validation labels for scoring.

    Seasonal Naive has no fitted parameters and does not consume these features.
    Features are a separately verified dataset for later models. Maturity masks
    are logged/reused, without pretending the baseline fits supervised samples.
    """
    origins = months_between(plan.validation_origin_start, plan.validation_origin_end)
    samples = forecast_samples(store.calendar, origins, plan.minimum_history_months)
    if tuple(sample.origin for sample in samples) != origins:
        raise ValueError("Validation origin/target calendar or minimum history is incomplete")
    if any(plan.target_partition(target) != "validation" for sample in samples for target in sample.targets):
        raise ValueError("Validation samples cross the frozen target boundaries")
    candidates = forecast_samples(store.calendar, store.calendar, plan.minimum_sample_history_months)
    fixed_scale = seasonal_scale(store.history_as_of(origins[0]), origins[0])
    prepared, vectors, folds, failures = [], [], [], []
    for sample in samples:
        history = store.history_as_of(sample.origin)
        mature = eligible_training_samples(candidates, sample.origin)
        store.assert_training_samples_available(mature, sample.origin)
        assert_no_target_overlap(mature, [sample])
        scale = seasonal_scale(history, sample.origin)
        fold = {
            "forecast_origin": sample.origin.strftime("%Y-%m"),
            "information_cutoff": sample.feature_cutoff.strftime("%Y-%m"),
            "available_history_n": len(history),
            "last_available_month": max(value.month for value in history).strftime("%Y-%m"),
            "mature_training_candidate_n": len(mature),
            "last_mature_training_origin": mature[-1].origin.strftime("%Y-%m") if mature else None,
            "supervised_model_fit": False,
            "mase_scale": scale.value, "mase_scale_status": scale.status,
            "seasonal_scale_pair_n": scale.pair_count,
            "fixed_initial_scale": fixed_scale.value,
            "fixed_initial_scale_status": fixed_scale.status,
            "fixed_initial_observed_through": fixed_scale.observed_through.strftime("%Y-%m") if fixed_scale.observed_through else None,
        }
        try:
            features = build_features(store, sample, spec)
            forecasts = predict(store, sample)
        except (FeatureUnavailableError, ForecastUnavailableError) as error:
            for horizon in sample.horizons:
                failures.append({"forecast_origin": sample.origin.strftime("%Y-%m"), "horizon": horizon, "stage": "feature_or_prediction", "reason": str(error)})
            folds.append({**fold, "prediction_status": "failed"})
            continue
        if len(features) != 3 or len(forecasts) != 3:
            raise ValueError("Incomplete feature/prediction output schema")
        vectors.extend(features)
        prepared.append((sample, forecasts, scale))
        folds.append({**fold, "prediction_status": "ready"})

    # Scorer capability stays here. Feature/model functions never receive it.
    actuals_reader = store.validation_actuals_reader()
    assessed_at = decision_at(plan.selection_freeze_origin)
    rows = []
    for sample, forecasts, scale in prepared:
        try:
            actuals = actuals_reader.actuals_for(sample, assessed_at)
        except LookupError as error:
            for horizon in sample.horizons:
                failures.append({"forecast_origin": sample.origin.strftime("%Y-%m"), "horizon": horizon, "stage": "scoring", "reason": str(error)})
            continue
        for forecast, actual in zip(forecasts, actuals):
            if forecast.target_month != actual.month or forecast.unit != actual.unit:
                raise ValueError("Scoring target or price-unit mismatch")
            error = actual.price - forecast.predicted_price
            rows.append({
                **forecast.record(), "actual_price": actual.price, "error": error, "absolute_error": abs(error),
                "mase_scale": scale.value, "mase_scale_status": scale.status,
                "scaled_error": abs(error) / scale.value if scale.value is not None else None,
                "fixed_initial_scale": fixed_scale.value,
                "fixed_initial_scaled_error": abs(error) / fixed_scale.value if fixed_scale.value is not None else None,
                "actual_available_at": actual.available_at.isoformat(),
                "assessed_at": assessed_at.isoformat(),
            })
    expected = {(sample.origin.strftime("%Y-%m"), h) for sample in samples for h in sample.horizons}
    actual_keys = {(row["forecast_origin"], row["horizon"]) for row in rows}
    if actual_keys - expected:
        raise ValueError("Unexpected origin/horizon keys in predictions")
    metrics = summarize_metrics(rows, len(expected))
    metrics["missing_origin_horizon_keys"] = [list(key) for key in sorted(expected - actual_keys)]
    metrics["failure_count"] = len(failures)
    metrics["complete"] = actual_keys == expected and len(rows) == len(expected)
    metrics["validation_origins"] = len(origins)
    metrics["unique_target_months"] = len({row["target_month"] for row in rows})
    return ValidationResult(tuple(rows), tuple(vectors), tuple(folds), tuple(failures), metrics)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_experiment(config_path: Path) -> dict:
    config_path = config_path.resolve()
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    if config.get("schema_version") != 1 or config["holdout_locked"] is not True or config["seasonal_period"] != 12:
        raise ValueError("Day 3 requires the locked holdout and seasonal period 12")
    if config["metrics"] != {
        "primary_mase_scale": "expanding_fold_asof", "comparison_mase_scale": "fixed_first_validation_asof",
        "aggregation": "equal_origin_horizon_pairs", "undefined_scale": "null_with_reason",
    }:
        raise ValueError("Unsupported metric protocol; no implicit overrides")
    root = (config_path.parent / config["project_root"]).resolve()

    def local(value: str) -> Path:
        result = (root / value).resolve()
        if not result.is_relative_to(root):
            raise ValueError("Config path escapes project root")
        return result

    split_path, day2_path = local(config["split_config"]), local(config["day2_config"])
    if _sha256(split_path) != config["split_config_sha256"] or _sha256(day2_path) != config["day2_config_sha256"]:
        raise ValueError("Frozen Day 2 config/split hash changed")
    plan, _ = load_split_plans(split_path)
    day2_config = tomllib.loads(day2_path.read_text(encoding="utf-8"))
    if local(day2_config["split_config"]) != split_path:
        raise ValueError("Day 2 loader and Day 3 must use exactly the same split file")
    feature_config = dict(config["features"])
    feature_config["lags"], feature_config["rolling_windows"] = tuple(feature_config["lags"]), tuple(feature_config["rolling_windows"])
    spec = FeatureSpec(**feature_config)
    store = load_development_store(root, day2_path)
    result = run_validation(store, plan, spec)
    if result.metrics["validation_origins"] != config["expected_origins"] or result.metrics["expected_pairs"] != config["expected_origin_horizon_pairs"]:
        raise ValueError("Unexpected validation date/count configuration")
    now = datetime.now(timezone.utc)
    destination = local(config["report_root"]) / now.strftime("%Y%m%dT%H%M%S%fZ")
    destination.mkdir(parents=True, exist_ok=False)

    def save_json(name: str, value: object) -> None:
        with (destination / name).open("x", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, ensure_ascii=False, indent=2, default=str, allow_nan=False)
            file.write("\n")

    def save_csv(name: str, records: list[dict] | tuple[dict, ...]) -> None:
        # Even on failure the exact JSON failure/missing-key reports are emitted.
        with (destination / name).open("x", encoding="utf-8", newline="") as file:
            if records:
                writer = csv.DictWriter(file, fieldnames=list(records[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(records)

    save_csv("validation_predictions.csv", result.rows)
    save_csv("validation_features.csv", [vector.record() for vector in result.feature_vectors])
    save_csv("fold_audit.csv", result.folds)
    save_json("feature_provenance.json", [vector.provenance() for vector in result.feature_vectors])
    save_json("metrics.json", result.metrics)
    save_json("failures.json", result.failures)
    source_manifest_path = local(day2_config["day1_manifest"])
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    package_root = Path(__file__).resolve().parents[1]
    code_files = [
        Path(__file__).resolve(), package_root / "evaluation/forecast_metrics.py",
        package_root / "evaluation/splits.py", package_root / "features/price.py",
        package_root / "forecasting/seasonal_naive.py", package_root / "data/availability.py",
        package_root / "data/audit.py", package_root / "data/world_bank.py", package_root / "data/_xlsx.py",
    ]
    save_json("run_manifest.json", {
        "created_at_utc": now.isoformat(), "python_version": sys.version,
        "stage": "day3_validation_seasonal_naive_only", "config_copy": config,
        "config_sha256": _sha256(config_path), "split_config_sha256": _sha256(split_path),
        "day2_config_sha256": _sha256(day2_path), "split_plan": asdict(plan),
        "day1_manifest_sha256": _sha256(source_manifest_path),
        "raw_snapshot_id": source_manifest["raw_snapshot_id"], "raw_sha256": source_manifest["raw_sha256"],
        "selected_processed_input": source_manifest["outputs"][source_manifest["selected_source_series"]],
        "code_sha256": {path.relative_to(package_root).as_posix(): _sha256(path) for path in code_files},
        "output_sha256": {path.name: _sha256(path) for path in sorted(destination.iterdir()) if path.is_file()},
        "dependencies": "Python standard library only", "random_seed": None,
        "seed_reason": "deterministic feature, forecast and metric calculations; no RNG",
        "vintage_mode": "latest_vintage_pseudo_real_time", "holdout_locked": True,
        "holdout_prices_or_scores_exported": False, "hyperparameter_search": False,
        "model_fitted_parameters": 0, "data_modified": False, "complete": result.metrics["complete"],
        "known_preexisting_sources": "Day 0-2 artifacts preserved; availability.py extended with validation-only scorer capability",
    })
    return {
        "report_dir": destination.relative_to(root).as_posix(), "complete": result.metrics["complete"],
        "validation_origins": result.metrics["validation_origins"], "evaluated_pairs": len(result.rows),
        "failures": len(result.failures), "by_horizon": result.metrics["by_horizon"],
        "overall": result.metrics["overall"], "holdout_locked": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    summary = run_experiment(args.config)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["complete"]:
        raise SystemExit(1)
