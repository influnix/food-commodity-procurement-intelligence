"""Fixed Day 4 fits with new native intervals and nine direct quantile models."""

from datetime import datetime
from time import perf_counter
import warnings

from food_procurement_intelligence.features.price import (
    checked_history, build_features, build_training_batch, FeatureUnavailableError,
)
from food_procurement_intelligence.evaluation.splits import months_between
from food_procurement_intelligence.forecasting.lightgbm import _train
from .contracts import UncertaintyPrediction


def _warnings(caught) -> list[dict]:
    return [{"category": w.category.__name__, "message": str(w.message)} for w in caught]


def sarimax_intervals(store, sample, config: dict, estimator_factory=None) -> tuple[tuple[UncertaintyPrediction, ...], list[dict]]:
    history = store.history_as_of(sample.origin)
    values = checked_history(history, sample.origin)
    end = max(values) if values else sample.feature_cutoff
    stamp = max(v.available_at for v in history) if history else datetime.min
    event = {"model": "sarimax", "forecast_origin": sample.origin.strftime("%Y-%m"), "horizon": "all",
             "status": "failed", "failure_reason": None, "train_n": len(values), "train_end": end.isoformat(),
             "fit_seconds": 0.0, "warnings": [], "converged": None, "api": "get_forecast(steps=4,signal_only=False).conf_int(alpha=.2)"}
    if (len(values) < config["minimum_history_months"] or not values
            or tuple(sorted(values)) != months_between(min(values), sample.feature_cutoff)
            or any(v.price is None for v in values.values())):
        event["failure_reason"] = "insufficient_or_missing_asof_history"
        return (), [event]
    if estimator_factory is None:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        estimator_factory = SARIMAX
    import numpy as np
    caught, started = [], perf_counter()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            estimator = estimator_factory(np.asarray([values[m].price for m in sorted(values)], dtype=float),
                order=tuple(config["order"]), seasonal_order=tuple(config["seasonal_order"]), trend=config["trend"],
                enforce_stationarity=config["enforce_stationarity"], enforce_invertibility=config["enforce_invertibility"])
            result = estimator.fit(method=config["method"], maxiter=config["maxiter"], disp=False)
            event["fit_seconds"] = perf_counter() - started
            event["converged"] = bool(result.mle_retvals.get("converged", False))
            if config["require_convergence"] and not event["converged"]:
                event["failure_reason"] = "nonconverged"
                return (), [event]
            forecast = result.get_forecast(steps=4, signal_only=False)
            center = np.asarray(forecast.predicted_mean, dtype=float).reshape(-1)
            bounds = np.asarray(forecast.conf_int(alpha=.2), dtype=float)
            legacy_center = np.asarray(result.forecast(steps=4), dtype=float).reshape(-1)
            if center.shape != (4,) or bounds.shape != (4, 2) or not np.array_equal(center, legacy_center):
                raise ValueError("Native interval center differs from the original forecast API")
            rows = tuple(UncertaintyPrediction(config["model_name"], "sarimax_native", sample.origin,
                sample.feature_cutoff, target, h, float(center[h]), float(bounds[h, 0]), float(center[h]),
                float(bounds[h, 1]), float(bounds[h, 0]), float(bounds[h, 1]), end, stamp)
                for h, target in zip(sample.horizons, sample.targets))
            event["status"] = "success"
            return rows, [event]
    except Exception as error:
        event["failure_reason"] = f"{type(error).__name__}: {error}"
        return (), [event]
    finally:
        event["warnings"] = _warnings(caught)
        event["wall_seconds"] = perf_counter() - started


def lightgbm_quantiles(store, sample, config: dict, spec, candidates, trainer=None):
    if config["label_mask"] != "complete_three_horizon_maturity" or config["early_stopping"] is not False:
        raise ValueError("Quantile models must preserve the Day 4 training mask")
    started = perf_counter()
    batch = build_training_batch(store, candidates, sample.origin, spec)
    current = build_features(store, sample, spec)
    history = checked_history(store.history_as_of(sample.origin), sample.origin)
    preparation_seconds = perf_counter() - started
    import_warnings = []
    if trainer is None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            import lightgbm  # noqa: F401
        import_warnings = _warnings(caught)
        trainer = _train
    import numpy as np
    predictions, events = [], []
    names = list(current[0].values)
    for h, target in zip(sample.horizons, sample.targets):
        pairs = [(v, y) for v, y in zip(batch.feature_vectors, batch.target_values) if v.horizon == h]
        event_base = {"model": "lightgbm", "forecast_origin": sample.origin.strftime("%Y-%m"),
                      "horizon": h, "train_n": len(pairs), "feature_names": names,
                      "preparation_seconds": preparation_seconds if h == 1 else 0.0,
                      "import_warnings": import_warnings if h == 1 else []}
        if len(pairs) < config["minimum_rows_per_horizon"]:
            events.append({**event_base, "status": "failed", "failure_reason": "insufficient_mature_rows", "warnings": []})
            continue
        vectors, labels = zip(*pairs)
        if any(v.target_month > sample.feature_cutoff or v.forecast_origin >= sample.origin for v in vectors):
            raise ValueError("Future label in quantile training batch")
        if any(list(v.values) != names for v in vectors) or len(names) != 15:
            raise ValueError("Day 3 feature schema changed")
        label_end = max(v.target_month for v in vectors)
        available_at = max(history[v.target_month].available_at for v in vectors)
        # The batch guard already checks all three labels, not just this h's end.
        event_base.update(feature_origin_start=min(v.forecast_origin for v in vectors).isoformat(),
                          feature_origin_end=max(v.forecast_origin for v in vectors).isoformat(),
                          train_end=label_end.isoformat(), max_label_available_at=available_at.isoformat())
        x = np.asarray([[v.values[name] for name in names] for v in vectors], dtype=float)
        y = np.asarray(labels, dtype=float)
        row = next(v for v in current if v.horizon == h)
        predict_x = np.asarray([[row.values[name] for name in names]], dtype=float)
        outputs = {}
        for quantile in (None, .1, .5, .9):
            params = dict(config["params"])
            if quantile is not None:
                params.update(objective="quantile", alpha=quantile)
            event = {**event_base, "quantile": quantile, "objective": params["objective"],
                     "alpha": params.get("alpha"), "status": "failed", "failure_reason": None,
                     "warnings": [], "fit_seconds": 0.0}
            # Preparation and import belong once per origin, not to all 12 fits.
            if quantile is not None:
                event["preparation_seconds"], event["import_warnings"] = 0.0, []
            events.append(event)
            caught, fit_start = [], perf_counter()
            try:
                if not all(np.isfinite(array).all() for array in (x, y, predict_x)):
                    raise ValueError("Nonfinite quantile training/prediction input")
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    estimator = trainer(x, y, names, params, config["num_boost_round"])
                    event["fit_seconds"] = perf_counter() - fit_start
                    output = np.asarray(estimator.predict(predict_x), dtype=float).reshape(-1)
                    if len(output) != 1 or not np.isfinite(output[0]):
                        raise ValueError("Missing or nonfinite quantile output")
                    outputs[quantile] = float(output[0])
                    event["status"] = "success"
            except Exception as error:
                event["failure_reason"] = f"{type(error).__name__}: {error}"
            finally:
                event["warnings"] = _warnings(caught)
        low, median, high = (outputs.get(q) for q in (.1, .5, .9))
        predictions.append(UncertaintyPrediction(config["model_name"], "lightgbm_quantile", sample.origin,
            sample.feature_cutoff, target, h, outputs.get(None), low, median, high, low, high, label_end, available_at))
    return tuple(predictions), events
