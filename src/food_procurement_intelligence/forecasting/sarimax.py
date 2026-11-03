"""Fixed-spec univariate SARIMAX, re-fitted using each origin's as-of history."""

from time import perf_counter
import warnings

from food_procurement_intelligence.features.price import checked_history
from food_procurement_intelligence.evaluation.splits import months_between
from .common import ModelFold, ModelPrediction


def fit_predict(store, sample, config: dict, estimator_factory=None) -> ModelFold:
    history = store.history_as_of(sample.origin)
    values = checked_history(history, sample.origin)
    event = {"model_name": config["model_name"], "forecast_origin": sample.origin.strftime("%Y-%m"),
             "horizon": "all", "train_n": len(history), "train_start": min(values).isoformat() if values else None,
             "train_end": max(values).isoformat() if values else None, "fit_seconds": 0.0, "predict_seconds": 0.0,
             "status": "failed", "failure_reason": None, "converged": None, "warnings": [], "config": config}
    if len(values) < config["minimum_history_months"]:
        return ModelFold((), ({**event, "failure_reason": "insufficient_history"},))
    if tuple(sorted(values)) != months_between(min(values), sample.feature_cutoff) or any(v.price is None for v in values.values()):
        return ModelFold((), ({**event, "failure_reason": "missing_or_unpublished_month; no interpolation"},))
    if estimator_factory is None:
        import_start = perf_counter()
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        estimator_factory = SARIMAX
        event["import_seconds"] = perf_counter() - import_start
    import numpy as np
    caught = []
    started = perf_counter()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            estimator = estimator_factory(
                np.asarray([values[m].price for m in sorted(values)], dtype=float),
                order=tuple(config["order"]), seasonal_order=tuple(config["seasonal_order"]),
                trend=config["trend"], enforce_stationarity=config["enforce_stationarity"],
                enforce_invertibility=config["enforce_invertibility"],
            )
            result = estimator.fit(method=config["method"], maxiter=config["maxiter"], disp=False)
            event["fit_seconds"] = perf_counter() - started
            event["converged"] = bool(result.mle_retvals.get("converged", False))
            event["iterations"] = int(result.mle_retvals.get("iterations", -1))
            if config["require_convergence"] and not event["converged"]:
                event["failure_reason"] = "nonconverged"
                return ModelFold((), (event,))
            predict_start = perf_counter()
            path = np.asarray(result.forecast(steps=4), dtype=float).reshape(-1)
            if len(path) != 4:
                raise ValueError("SARIMAX must produce exactly four steps")
            predictions = tuple(ModelPrediction(sample.origin, sample.feature_cutoff, target, h,
                                                 float(path[h]), config["model_name"])
                                for h, target in zip(sample.horizons, sample.targets))
            event["predict_seconds"] = perf_counter() - predict_start
            event["status"] = "success"
            return ModelFold(predictions, (event,))
    except Exception as error:
        if not event["fit_seconds"]:
            event["fit_seconds"] = perf_counter() - started
        event["failure_reason"] = f"{type(error).__name__}: {error}"
        return ModelFold((), (event,))
    finally:
        event["warnings"] = [{"category": warning.category.__name__, "message": str(warning.message)} for warning in caught]
