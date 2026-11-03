"""Three fixed direct LightGBM models trained on mature Day 3 TrainingBatch."""

from collections import Counter
from time import perf_counter
import warnings

from food_procurement_intelligence.features.price import build_features, build_training_batch
from .common import ModelFold, ModelPrediction


def _train(values, labels, names, params, rounds):
    import lightgbm as lgb
    data = lgb.Dataset(values, label=labels, feature_name=names)
    # No valid_sets/callbacks/early stopping; current validation labels stay outside.
    return lgb.train(dict(params), data, num_boost_round=rounds)


def fit_predict(store, sample, config: dict, spec, candidates, trainer=None) -> ModelFold:
    if config["label_mask"] != "complete_three_horizon_maturity" or config["early_stopping"] is not False:
        raise ValueError("LightGBM requires the fixed complete-vector mask without early stopping")
    # These existing guards reject holdout origins and all unpublished labels.
    preparation_start = perf_counter()
    batch = build_training_batch(store, candidates, sample.origin, spec)
    current = build_features(store, sample, spec)
    preparation_seconds = perf_counter() - preparation_start
    import_warnings, import_seconds = [], 0.0
    if trainer is None:
        import_start = perf_counter()
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            import lightgbm  # noqa: F401; initialize outside the fit timer
        import_seconds = perf_counter() - import_start
        import_warnings = [{"category": w.category.__name__, "message": str(w.message)} for w in recorded]
        trainer = _train
    import numpy as np
    predictions, events = [], []
    names = list(current[0].values)
    for horizon, target in zip(sample.horizons, sample.targets):
        pairs = [(vector, label) for vector, label in zip(batch.feature_vectors, batch.target_values) if vector.horizon == horizon]
        event = {"model_name": config["model_name"], "forecast_origin": sample.origin.strftime("%Y-%m"),
                 "horizon": horizon, "train_n": len(pairs), "fit_seconds": 0.0, "predict_seconds": 0.0,
                 "status": "failed", "failure_reason": None, "warnings": [], "config": config,
                 "excluded_sample_counts": dict(Counter(item["reason"] for item in batch.excluded_samples)),
                 "feature_names": names}
        event["batch_preparation_seconds"] = preparation_seconds if horizon == sample.horizons[0] else 0.0
        event["import_seconds"] = import_seconds if horizon == sample.horizons[0] else 0.0
        event["import_warnings"] = import_warnings if horizon == sample.horizons[0] else []
        events.append(event)
        if len(pairs) < config["minimum_rows_per_horizon"]:
            event["failure_reason"] = "insufficient_mature_training_rows"
            continue
        vectors, labels = zip(*pairs)
        if any(list(vector.values) != names for vector in vectors):
            raise ValueError("Training/prediction feature schema mismatch")
        if any(vector.target_month > sample.feature_cutoff or vector.forecast_origin >= sample.origin for vector in vectors):
            raise ValueError("Training target or origin violates as-of cutoff")
        event.update({"feature_origin_start": min(v.forecast_origin for v in vectors).isoformat(),
                      "feature_origin_end": max(v.forecast_origin for v in vectors).isoformat(),
                      "last_target_month": max(v.target_month for v in vectors).isoformat(),
                      "max_feature_observation_month": max(month for v in vectors for months in v.observed_dependencies.values() for month in months).isoformat()})
        x = np.asarray([[vector.values[name] for name in names] for vector in vectors], dtype=float)
        y = np.asarray(labels, dtype=float)
        row = next(vector for vector in current if vector.horizon == horizon)
        predict_x = np.asarray([[row.values[name] for name in names]], dtype=float)
        if not all(np.isfinite(array).all() for array in (x, y, predict_x)):
            event["failure_reason"] = "nonfinite_training_or_prediction_input"
            continue
        started, caught = perf_counter(), []
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                estimator = trainer(x, y, names, dict(config["params"]), config["num_boost_round"])
                event["fit_seconds"] = perf_counter() - started
                predict_start = perf_counter()
                output = np.asarray(estimator.predict(predict_x), dtype=float).reshape(-1)
                if len(output) != 1:
                    raise ValueError("Direct model must return one prediction")
                predictions.append(ModelPrediction(sample.origin, sample.feature_cutoff, target, horizon,
                                                   float(output[0]), config["model_name"]))
                event["predict_seconds"] = perf_counter() - predict_start
                event["status"] = "success"
        except Exception as error:
            if not event["fit_seconds"]:
                event["fit_seconds"] = perf_counter() - started
            event["failure_reason"] = f"{type(error).__name__}: {error}"
        finally:
            event["warnings"] = [{"category": warning.category.__name__, "message": str(warning.message)} for warning in caught]
    return ModelFold(tuple(predictions), tuple(events))
