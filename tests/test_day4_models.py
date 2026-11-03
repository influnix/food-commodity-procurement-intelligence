"""Offline hand-checked model inputs and failure/coverage contracts."""

from dataclasses import replace
from datetime import date
from pathlib import Path
import tomllib
import warnings

import numpy as np
import pytest

from food_procurement_intelligence.data.availability import DevelopmentPriceStore
from food_procurement_intelligence.data.world_bank import PriceObservation, assumed_available_at
from food_procurement_intelligence.evaluation.splits import ForecastSample, add_months, load_split_plans, months_between, HoldoutLockedError
from food_procurement_intelligence.forecasting.common import ModelPrediction, ModelFold, adapt_seasonal_prediction
from food_procurement_intelligence.forecasting.sarimax import fit_predict
from food_procurement_intelligence.forecasting.seasonal_naive import predict
from food_procurement_intelligence.forecasting.lightgbm import fit_predict as fit_lightgbm
from food_procurement_intelligence.features.price import FeatureSpec
from food_procurement_intelligence.features.price import FeatureUnavailableError
from food_procurement_intelligence.evaluation.splits import forecast_samples
from food_procurement_intelligence.evaluation.model_backtesting import evaluate_model
from food_procurement_intelligence.evaluation.model_comparison import compare_rows

ROOT = Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((ROOT / "configs/day4.toml").read_text(encoding="utf-8"))


@pytest.fixture
def context():
    plan, _ = load_split_plans(ROOT / "configs/splits.toml")
    rows = [PriceObservation(month, month.strftime("%Y-%m"), 100.0 + i, "wheat", "USD_per_metric_tonne",
                             "Wheat, US HRW", "($/mt)", "TOY", str(i), str(100.0 + i), False,
                             assumed_available_at(month), "assumed", "TOY_NOT_REAL")
            for i, month in enumerate(months_between(plan.data_start, plan.data_end))]
    origin = plan.validation_origin_start
    sample = ForecastSample(origin, (1, 2, 3), tuple(add_months(origin, h) for h in (1, 2, 3)))
    return plan, rows, sample


class FakeSARIMAX:
    inputs = []
    mle_retvals = {"converged": True, "iterations": 2}

    def __init__(self, values, **kwargs):
        self.inputs.append((values.copy(), kwargs))

    def fit(self, **kwargs):
        return self

    def forecast(self, steps):
        assert steps == 4
        return np.array([501.0, 502.0, 503.0, 504.0])


def test_sarimax_history_and_four_step_mapping(context):
    plan, rows, sample = context
    store = DevelopmentPriceStore(rows, plan)
    FakeSARIMAX.inputs = []
    fold = fit_predict(store, sample, CONFIG["sarimax"], FakeSARIMAX)
    assert [prediction.predicted_price for prediction in fold.predictions] == [502, 503, 504]
    assert len(FakeSARIMAX.inputs[0][0]) == 737
    assert fold.events[0]["train_end"] == "2021-05-01"
    later = ForecastSample(add_months(sample.origin, 1), (1, 2, 3), tuple(add_months(sample.origin, h + 1) for h in (1, 2, 3)))
    fit_predict(store, later, CONFIG["sarimax"], FakeSARIMAX)
    assert len(FakeSARIMAX.inputs[-1][0]) == 738


def test_sarimax_future_values_never_change_fit_input(context):
    plan, rows, sample = context
    future = [replace(row, price=1e100) if row.date >= sample.origin else row for row in rows]
    FakeSARIMAX.inputs = []
    a = fit_predict(DevelopmentPriceStore(rows, plan), sample, CONFIG["sarimax"], FakeSARIMAX)
    b = fit_predict(DevelopmentPriceStore(future, plan), sample, CONFIG["sarimax"], FakeSARIMAX)
    assert np.array_equal(FakeSARIMAX.inputs[0][0], FakeSARIMAX.inputs[1][0])
    assert a.predictions == b.predictions


def test_sarimax_warning_and_nonconvergence_recorded_without_fallback(context):
    plan, rows, sample = context

    class Nonconverged(FakeSARIMAX):
        mle_retvals = {"converged": False}

        def fit(self, **kwargs):
            warnings.warn("toy convergence warning", RuntimeWarning)
            return self

    fold = fit_predict(DevelopmentPriceStore(rows, plan), sample, CONFIG["sarimax"], Nonconverged)
    assert not fold.predictions
    assert fold.events[0]["failure_reason"] == "nonconverged"
    assert fold.events[0]["warnings"][0]["message"] == "toy convergence warning"


def test_sarimax_fitting_exception_is_explicit(context):
    plan, rows, sample = context

    class Broken(FakeSARIMAX):
        def fit(self, **kwargs):
            raise RuntimeError("toy fitting failure")

    fold = fit_predict(DevelopmentPriceStore(rows, plan), sample, CONFIG["sarimax"], Broken)
    assert not fold.predictions and "toy fitting failure" in fold.events[0]["failure_reason"]


def test_sarimax_missing_month_and_holdout_are_blocked(context):
    plan, rows, sample = context
    missing = [row for row in rows if row.date != add_months(sample.origin, -1)]
    fold = fit_predict(DevelopmentPriceStore(missing, plan), sample, CONFIG["sarimax"], FakeSARIMAX)
    assert not fold.predictions and "missing" in fold.events[0]["failure_reason"]
    holdout = ForecastSample(plan.selection_freeze_origin, (1, 2, 3), tuple(add_months(plan.selection_freeze_origin, h) for h in (1, 2, 3)))
    with pytest.raises(HoldoutLockedError):
        fit_predict(DevelopmentPriceStore(rows, plan), holdout, CONFIG["sarimax"], FakeSARIMAX)


def test_common_schema_and_seasonal_adapter(context):
    plan, rows, sample = context
    original = predict(DevelopmentPriceStore(rows, plan), sample)[0]
    adapted = adapt_seasonal_prediction(original)
    assert adapted.predicted_price == original.predicted_price
    assert {"forecast_origin", "information_cutoff", "target_month", "horizon", "predicted_price", "model_name", "forecast_asof_at", "unit"} <= adapted.record().keys()
    with pytest.raises(ValueError):
        replace(adapted, predicted_price=float("nan"))
    with pytest.raises(ValueError):
        replace(adapted, target_month=sample.origin)


class FakeBooster:
    def __init__(self, value):
        self.value = value

    def predict(self, x):
        return np.array([self.value])


def test_direct_labels_features_and_conservative_common_mask(context):
    plan, rows, sample = context
    store = DevelopmentPriceStore(rows, plan)
    candidates = forecast_samples(store.calendar, store.calendar, 1)
    calls = []

    def trainer(x, y, names, params, rounds):
        calls.append((x.copy(), y.copy(), names, params, rounds))
        assert params["num_threads"] == 1 and rounds == 100
        return FakeBooster(y[-1])

    fold = fit_lightgbm(store, sample, CONFIG["lightgbm"], FeatureSpec(), candidates, trainer)
    assert len(fold.predictions) == len(calls) == 3
    assert [event["train_n"] for event in fold.events] == [721, 721, 721]
    assert [event["last_target_month"] for event in fold.events] == ["2021-03-01", "2021-04-01", "2021-05-01"]
    assert all(event["feature_origin_end"] == "2021-02-01" for event in fold.events)
    assert calls[1][1][-1] == calls[0][1][-1] + 1
    assert calls[2][1][-1] == calls[0][1][-1] + 2
    assert all(call[0].shape == (721, 15) for call in calls)
    assert all(event["max_feature_observation_month"] == "2021-01-01" for event in fold.events)


def test_lightgbm_future_values_and_holdout_do_not_reach_trainer(context):
    plan, rows, sample = context
    poisoned = [replace(row, price=1e100) if row.date >= sample.origin else row for row in rows]
    calls = []

    def trainer(x, y, names, params, rounds):
        calls.append((x.copy(), y.copy()))
        return FakeBooster(float(y.mean()))

    output = []
    for values in (rows, poisoned):
        store = DevelopmentPriceStore(values, plan)
        output.append(fit_lightgbm(store, sample, CONFIG["lightgbm"], FeatureSpec(), forecast_samples(store.calendar, store.calendar, 1), trainer))
    assert output[0].predictions == output[1].predictions
    assert all(np.array_equal(calls[h][0], calls[h+3][0]) and np.array_equal(calls[h][1], calls[h+3][1]) for h in range(3))
    store = DevelopmentPriceStore(rows, plan)
    holdout = ForecastSample(plan.selection_freeze_origin, (1, 2, 3), tuple(add_months(plan.selection_freeze_origin, h) for h in (1, 2, 3)))
    with pytest.raises(HoldoutLockedError):
        fit_lightgbm(store, holdout, CONFIG["lightgbm"], FeatureSpec(), forecast_samples(store.calendar, store.calendar, 1), trainer)


def test_lightgbm_exception_and_nonfinite_prediction_are_failures(context):
    plan, rows, sample = context
    store = DevelopmentPriceStore(rows, plan)
    candidates = forecast_samples(store.calendar, store.calendar, 1)

    def broken(*_):
        raise RuntimeError("toy failure")

    failed = fit_lightgbm(store, sample, CONFIG["lightgbm"], FeatureSpec(), candidates, broken)
    assert not failed.predictions and len(failed.events) == 3
    nan = fit_lightgbm(store, sample, CONFIG["lightgbm"], FeatureSpec(), candidates, lambda *_: FakeBooster(float("nan")))
    assert not nan.predictions and all(event["status"] == "failed" for event in nan.events)


def test_real_lightgbm_fixed_seed_repeatability_without_validation_labels(context):
    pytest.importorskip("lightgbm")
    plan, rows, sample = context
    store = DevelopmentPriceStore(rows, plan)
    candidates = forecast_samples(store.calendar, store.calendar, 1)
    a = fit_lightgbm(store, sample, CONFIG["lightgbm"], FeatureSpec(), candidates)
    b = fit_lightgbm(store, sample, CONFIG["lightgbm"], FeatureSpec(), candidates)
    assert len(a.predictions) == 3 and a.predictions == b.predictions


def test_real_sarimax_small_seeded_series(context):
    pytest.importorskip("statsmodels")
    plan, rows, sample = context
    rng = np.random.default_rng(912)
    noisy = [replace(row, price=float(100 + i * .05 + 5 * np.sin(i / 2) + rng.normal(0, 2))) for i, row in enumerate(rows)]
    result = fit_predict(DevelopmentPriceStore(noisy, plan), sample, CONFIG["sarimax"])
    assert len(result.predictions) == 3 and result.events[0]["converged"]


def _comparison_row(origin, horizon, target, error):
    return {"forecast_origin": origin, "horizon": horizon, "target_month": target,
            "actual_price": 100.0, "predicted_price": 100.0 - error, "unit": "USD_per_metric_tonne",
            "mase_scale": 2.0, "error": error, "scaled_error": abs(error) / 2,
            "fixed_initial_scaled_error": abs(error) / 2}


def test_comparison_improvement_and_same_target_different_origin():
    baseline = [_comparison_row("2020-01", 2, "2020-03", 4), _comparison_row("2020-02", 1, "2020-03", 6)]
    better = [dict(row, error=row["error"] / 2, scaled_error=row["scaled_error"] / 2) for row in baseline]
    result = compare_rows({"baseline": baseline, "better": better}, "baseline")
    overall = next(row for row in result["model_success_table"] if row["Model"] == "better" and row["Horizon"] == "Overall")
    assert overall["MAE"] == 2.5 and overall["MASE"] == 1.25
    assert overall["MAE_improvement_pct"] == overall["MASE_improvement_pct"] == 50
    assert result["common_success_keys"] == 2


def test_incomplete_model_not_ranked_against_full_baseline():
    baseline = [_comparison_row("2020-01", 2, "2020-03", 4), _comparison_row("2020-02", 1, "2020-03", 6)]
    result = compare_rows({"baseline": baseline, "partial": baseline[:1]}, "baseline")
    own = next(row for row in result["model_success_table"] if row["Model"] == "partial" and row["Horizon"] == "Overall")
    assert own["Failure"] == 1 and own["MAE_improvement_pct"] is None
    assert result["common_success_keys"] == 1
    assert all(row["N"] == 1 for row in result["common_success_table"] if row["Horizon"] == "Overall")


@pytest.mark.parametrize("field,value", [("actual_price", 999), ("mase_scale", 999), ("unit", "USD/kg"), ("target_month", "2099-01")])
def test_comparison_refuses_inconsistent_actual_scale_unit_or_target(field, value):
    baseline = [_comparison_row("2020-01", 1, "2020-02", 4)]
    with pytest.raises(ValueError):
        compare_rows({"baseline": baseline, "wrong": [dict(baseline[0], **{field: value})]}, "baseline")


def test_model_evaluator_waits_for_all_fits_and_records_missing_key(context, monkeypatch):
    plan, rows, sample = context
    store = DevelopmentPriceStore(rows, plan)
    calls = []
    original_reader = store.validation_actuals_reader

    def predictor(store_arg, current, config):
        history = store_arg.history_as_of(current.origin)
        calls.append(current.origin)
        predictions = tuple(ModelPrediction(current.origin, current.feature_cutoff, target, h,
                                             history[-1].price, config["model_name"])
                            for h, target in zip(current.horizons, current.targets)
                            if not (current.origin == sample.origin and h == 3))
        return ModelFold(predictions, ({"fit_seconds": 0.0, "status": "success", "warnings": []},))

    def reader():
        assert len(calls) == 36
        return original_reader()

    monkeypatch.setattr(store, "validation_actuals_reader", reader)
    result = evaluate_model(store, plan, FeatureSpec(), CONFIG["sarimax"], "sarimax", predictor)
    assert len(result["rows"]) == 107 and not result["metrics"]["complete"]
    assert result["metrics"]["missing_keys"] == [["2021-06", 3]]


def test_missing_current_feature_is_a_logged_failed_fold(context):
    plan, rows, sample = context

    def missing(*args):
        raise FeatureUnavailableError("toy current lookback unavailable")

    result = evaluate_model(DevelopmentPriceStore(rows, plan), plan, FeatureSpec(), CONFIG["lightgbm"], "lightgbm", missing)
    assert not result["metrics"]["complete"] and len(result["metrics"]["missing_keys"]) == 108
    assert len(result["events"]) == 36
    assert all("toy current lookback" in event["failure_reason"] for event in result["events"])
