"""Offline toy-only uncertainty, OOF availability and hand-calculated metrics."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import tomllib

import numpy as np
import pytest

from food_procurement_intelligence.data.availability import DevelopmentPriceStore
from food_procurement_intelligence.data.world_bank import PriceObservation, assumed_available_at
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample, add_months, decision_at, forecast_samples, load_split_plans, months_between,
    LeakageError, HoldoutLockedError,
)
from food_procurement_intelligence.features.price import FeatureSpec
from food_procurement_intelligence.uncertainty.contracts import UncertaintyPrediction
from food_procurement_intelligence.uncertainty.calibration import (
    OOFResidual, OOFPool, assert_residual_available, calibrate, finite_sample_adjustment,
)
from food_procurement_intelligence.uncertainty.models import sarimax_intervals, lightgbm_quantiles
from food_procurement_intelligence.evaluation.uncertainty_backtesting import (
    generate_uncertainty, evaluate_uncertainty, load_uncertainty_context, risk_signal,
)
from food_procurement_intelligence.evaluation.uncertainty_metrics import (
    pinball, score_predictions, summarize_uncertainty,
)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
D4 = tomllib.loads((ROOT / "configs/forecasting/models.toml").read_text(encoding="utf-8"))
D5 = tomllib.loads((ROOT / "configs/scenarios/calibration.toml").read_text(encoding="utf-8"))


@pytest.fixture
def toy():
    plan, _ = load_split_plans(ROOT / "configs/evaluation/splits.toml")
    records = [PriceObservation(m, m.strftime("%Y-%m"), 100.0 + i / 10, "wheat", "USD_per_metric_tonne",
        "Wheat, US HRW", "($/mt)", "TOY", str(i), str(100 + i / 10), False,
        assumed_available_at(m), "assumed_toy", "TOY_NOT_REAL")
        for i, m in enumerate(months_between(plan.data_start, plan.data_end))]
    sample = ForecastSample(plan.validation_origin_start, (1, 2, 3),
                            tuple(add_months(plan.validation_origin_start, h) for h in (1, 2, 3)))
    return plan, records, sample


def prediction(origin=date(2021, 6, 1), horizon=1, model="sarimax_110_10012", method="sarimax_native", low=90., median=100., high=110.):
    cutoff = add_months(origin, -1)
    return UncertaintyPrediction(model, method, origin, cutoff, add_months(origin, horizon), horizon,
                                  100., low, median, high, low, high, cutoff, decision_at(origin))


def residual(origin=date(2020, 1, 1), h=1, release=date(2021, 6, 1), **changes):
    target = add_months(origin, h)
    result = OOFResidual(origin, target, h, decision_at(add_months(target, 1)), "sarimax_110_10012",
        "sarimax_native", 20., 10., 120., add_months(origin, -1), decision_at(origin), release, "historical_train")
    return replace(result, **changes)


@pytest.mark.parametrize("change", [
    {"information_cutoff": date(2021, 6, 1)},
    {"fit_information_end": date(2021, 7, 1)},
    {"fit_max_label_available_at": decision_at(date(2021, 6, 1)) + timedelta(seconds=1)},
])
def test_uncertainty_contract_rejects_future_fit_information(change):
    with pytest.raises(LeakageError):
        replace(prediction(), **change)


def test_native_step_mapping_and_mean_agrees_with_original_forecast(toy):
    plan, records, sample = toy
    inputs = []

    class Fake:
        mle_retvals = {"converged": True}

        def __init__(self, values, **kwargs):
            inputs.append(values.copy())

        def fit(self, **kwargs):
            assert kwargs["maxiter"] == 100
            return self

        def forecast(self, steps):
            return np.array([100., 200., 300., 400.])

        def get_forecast(self, steps, signal_only):
            assert steps == 4 and signal_only is False

            def bounds(alpha):
                assert alpha == .2
                return np.array([[90., 110.], [180., 220.], [270., 330.], [360., 440.]])

            return SimpleNamespace(predicted_mean=self.forecast(steps), conf_int=bounds)

    result, events = sarimax_intervals(DevelopmentPriceStore(records, plan), sample, D4["sarimax"], Fake)
    assert len(inputs[0]) == 737
    assert [r.point_prediction for r in result] == [200, 300, 400]
    assert [r.lower_bound for r in result] == [180, 270, 360]
    assert events[0]["status"] == "success"


def test_native_failures_nonconvergence_and_forecast_api_center_mismatch(toy):
    plan, records, sample = toy

    class Fake:
        mle_retvals = {"converged": False}

        def __init__(self, *args, **kwargs):
            pass

        def fit(self, **kwargs):
            return self

    out, events = sarimax_intervals(DevelopmentPriceStore(records, plan), sample, D4["sarimax"], Fake)
    assert not out and events[0]["failure_reason"] == "nonconverged"

    class Mismatch(Fake):
        mle_retvals = {"converged": True}

        def forecast(self, steps):
            return np.ones(4) * 2

        def get_forecast(self, **kwargs):
            return SimpleNamespace(predicted_mean=np.ones(4), conf_int=lambda **kwargs: np.ones((4, 2)))

    out, events = sarimax_intervals(DevelopmentPriceStore(records, plan), sample, D4["sarimax"], Mismatch)
    assert not out and "center differs" in events[0]["failure_reason"]


def test_negative_bounds_preserved_and_crossing_invalid_not_silently_repaired():
    negative = replace(prediction(), lower_bound=-5, q10=-5)
    assert negative.interval_usable and negative.lower_bound == -5
    assert "nonpositive" in negative.validity_status
    crossed = prediction(low=110, median=100, high=120)
    assert crossed.crossing and not crossed.interval_usable
    assert "quantile_crossing" in crossed.validity_status
    bad = replace(prediction(), upper_bound=float("inf"))
    assert not bad.interval_usable and bad.record()["upper_bound"] is None


def test_quantile_trainer_objective_alpha_mask_and_future_invariance(toy):
    plan, records, sample = toy
    calls = []

    def trainer(x, y, names, params, rounds):
        calls.append((x.copy(), y.copy(), params.copy()))
        assert x.shape == (721, 15) and len(names) == 15 and rounds == 100
        assert params["seed"] == 20261027 and params["num_threads"] == 1
        value = float(y.mean() + params.get("alpha", .5))
        return SimpleNamespace(predict=lambda x: np.array([value]))

    outputs = []
    changed = [replace(r, price=1e80) if r.date >= sample.origin else r for r in records]
    for rows in (records, changed):
        store = DevelopmentPriceStore(rows, plan)
        out, events = lightgbm_quantiles(store, sample, D4["lightgbm"], FeatureSpec(),
                                        forecast_samples(store.calendar, store.calendar, 1), trainer)
        outputs.append(out)
        assert [e["train_end"] for e in events[::4]] == ["2021-03-01", "2021-04-01", "2021-05-01"]
    assert outputs[0] == outputs[1]
    for block in (calls[:12], calls[12:]):
        assert [c[2]["objective"] for c in block] == ["regression_l2", "quantile", "quantile", "quantile"] * 3
        assert [c[2].get("alpha") for c in block] == [None, .1, .5, .9] * 3
    assert all(np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1]) for a, b in zip(calls[:12], calls[12:]))


def test_quantile_failure_leaves_missing_bound_and_no_model_fallback(toy):
    plan, records, sample = toy

    def trainer(x, y, names, params, rounds):
        if params.get("alpha") == .1:
            raise RuntimeError("toy quantile fit failed")
        return SimpleNamespace(predict=lambda x: np.array([100.]))

    store = DevelopmentPriceStore(records, plan)
    out, events = lightgbm_quantiles(store, sample, D4["lightgbm"], FeatureSpec(),
                                    forecast_samples(store.calendar, store.calendar, 1), trainer)
    assert len(out) == 3 and all(r.q10 is None and not r.interval_usable for r in out)
    assert sum(e["status"] == "failed" for e in events) == 3


def test_real_quantile_models_repeat_deterministically_on_toy(toy):
    plan, records, sample = toy
    store = DevelopmentPriceStore(records, plan)
    args = (store, sample, D4["lightgbm"], FeatureSpec(), forecast_samples(store.calendar, store.calendar, 1))
    a, _ = lightgbm_quantiles(*args)
    b, _ = lightgbm_quantiles(*args)
    assert a == b and len(a) == 3
    assert any(r.q50 != r.point_prediction for r in a)


def test_residual_origin_horizon_and_in_sample_proof_rejected():
    with pytest.raises(LeakageError):
        replace(residual(), residual_horizon=3)
    with pytest.raises(LeakageError):
        replace(residual(), fit_information_end=date(2020, 2, 1))
    with pytest.raises(LeakageError):
        replace(residual(), fit_max_label_available_at=decision_at(date(2020, 2, 1)))


def test_future_target_and_timestamp_residual_blocked(toy):
    plan, _, _ = toy
    r = residual(origin=date(2021, 3, 1), h=3, release=date(2021, 7, 1))
    with pytest.raises(LeakageError):
        assert_residual_available(r, date(2021, 6, 1), plan)
    assert_residual_available(r, date(2021, 7, 1), plan)
    delayed = replace(r, residual_actual_available_at=decision_at(date(2021, 8, 1)), first_released_at_origin=date(2021, 8, 1))
    with pytest.raises(LeakageError):
        assert_residual_available(delayed, date(2021, 7, 1), plan)


def test_pool_release_does_not_access_unpublished_target_and_keeps_h_separate(toy):
    plan, records, _ = toy
    origin = date(2021, 3, 1)
    target = date(2021, 6, 1)
    rows = [replace(r, available_at=decision_at(date(2021, 8, 1)).isoformat()) if r.date == target else r for r in records]
    pool = OOFPool(plan)
    store = DevelopmentPriceStore(rows, plan)
    pool.release(store, origin)
    pool.add([prediction(origin, h) for h in (1, 2, 3)], "historical_train")
    pool.release(store, date(2021, 6, 1))
    assert {r.residual_horizon for r in pool.released.values()} == {1, 2}
    pool.release(store, date(2021, 7, 1))
    assert len(pool.released) == 2  # June date is old, publication still too late.
    pool.release(store, date(2021, 8, 1))
    assert len(pool.released) == 3


def test_holdout_and_historical_partition_guard_and_duplicate_oof(toy):
    plan, records, _ = toy
    pool = OOFPool(plan)
    with pytest.raises(HoldoutLockedError):
        pool.add([prediction(date(2024, 9, 1))], "validation")
    with pytest.raises(LeakageError):
        pool.add([prediction(date(2021, 6, 1))], "historical_train")
    pool.add([prediction(date(2021, 3, 1))], "historical_train")
    with pytest.raises(ValueError):
        pool.add([prediction(date(2021, 3, 1))], "historical_train")
    r = residual(origin=date(2024, 9, 1), release=date(2024, 11, 1), phase="validation")
    with pytest.raises(HoldoutLockedError):
        assert_residual_available(r, date(2024, 11, 1), plan)


def test_finite_sample_quantile_hand_rank_and_insufficient_fallback(toy):
    assert finite_sample_adjustment(list(range(24)), .8, 24) == (19, 20)
    assert finite_sample_adjustment(list(range(60)), .8, 24) == (48, 49)
    assert finite_sample_adjustment([1.], .8, 1) == (None, 2)
    assert finite_sample_adjustment([1.] * 23, .8, 24)[0] is None
    plan, _, _ = toy
    corrected, audit = calibrate(prediction(), [], plan, D5)
    assert corrected.calibration_status == "insufficient_raw_fallback"
    assert corrected.lower_bound == 90 and corrected.upper_bound == 110
    assert corrected.q10 is None and corrected.base_q10 == 90 and audit["selected_n"] == 0


def test_model_and_horizon_pools_are_not_mixed_or_future_silently_accepted(toy):
    plan, _, _ = toy
    residuals = [residual(add_months(date(2018, 1, 1), i), h=h) for i in range(24) for h in (1, 2, 3)]
    corrected, audit = calibrate(prediction(), residuals, plan, D5)
    assert corrected.calibration_sample_size == 24 and audit["adjustment"] == 10
    assert corrected.lower_bound == 80 and corrected.upper_bound == 120
    other = replace(prediction(), model_name="other")
    assert calibrate(other, residuals, plan, D5)[0].calibration_status == "insufficient_raw_fallback"
    future = residual(origin=date(2021, 3, 1), h=3, release=date(2021, 7, 1))
    with pytest.raises(LeakageError):
        calibrate(prediction(), residuals + [future], plan, D5)
    with pytest.raises(ValueError):
        calibrate(prediction(), residuals + residuals[:1], plan, D5)


def test_raw_crossing_not_laundered_by_interval_only_calibration(toy):
    plan, _, _ = toy
    p = prediction(low=110, median=100, high=120)
    corrected, audit = calibrate(p, [], plan, D5)
    assert corrected.calibration_status == "raw_invalid_uncalibrated"
    assert not corrected.interval_usable and corrected.lower_bound is None


def toy_predictors(calls=None):
    def sar(store, sample, config):
        if calls is not None:
            calls.append(sample.origin)
        last = store.history_as_of(sample.origin)[-1]
        p = tuple(replace(prediction(sample.origin, h, config["model_name"], "sarimax_native",
            low=last.price - 1, median=last.price, high=last.price + 1), point_prediction=last.price)
            for h in sample.horizons)
        return p, []

    def lgb(store, sample, config, spec, candidates):
        out, events = sar(store, sample, config)
        return tuple(replace(p, uncertainty_method="lightgbm_quantile") for p in out), events

    return {"sarimax": sar, "lightgbm": lgb}


def test_full_calendar_oof_is_train_only_and_minimum_first_fold_counts(toy):
    plan, records, _ = toy
    generated = generate_uncertainty(DevelopmentPriceStore(records, plan), plan, FeatureSpec(), D4, D5,
                                      predictors=toy_predictors())
    assert len(generated["raw_oof"]) == 96 * 6
    assert len(generated["predictions"]) == 432
    for row in generated["raw_oof"]:
        if row["phase"] == "historical_train":
            assert row["target_month"] <= "2021-06" and row["fit_information_end"] < row["forecast_origin"]
    first = [r for r in generated["audits"] if r["calibration_origin"] == "2021-06" and r["model_name"] == D4["sarimax"]["model_name"]]
    assert [r["selected_n"] for r in first] == [60, 60, 59]
    assert len([r for r in generated["residuals"] if r["phase"] == "historical_train"]) == 360
    assert all(r["residual_target_month"] <= "2024-04" for r in generated["residuals"])


@pytest.mark.parametrize("poison", ["future_validation", "holdout"])
def test_future_truth_changes_do_not_change_prior_uncertainty_or_any_holdout_output(toy, poison):
    plan, records, _ = toy
    threshold = date(2022, 1, 1) if poison == "future_validation" else plan.holdout_target_start
    changed = [replace(r, price=999999.) if r.date >= threshold else r for r in records]
    outputs = [generate_uncertainty(DevelopmentPriceStore(rows, plan), plan, FeatureSpec(), D4, D5,
                                    predictors=toy_predictors()) for rows in (records, changed)]
    before = lambda p: poison == "holdout" or p.forecast_origin <= threshold
    assert [p for p in outputs[0]["predictions"] if before(p)] == [p for p in outputs[1]["predictions"] if before(p)]
    if poison == "holdout":
        assert outputs[0] == outputs[1]


def test_evaluator_waits_for_all_forecasts_and_uses_same_108_actuals(toy, monkeypatch):
    plan, records, _ = toy
    store, calls = DevelopmentPriceStore(records, plan), []
    original = store.validation_actuals_reader

    def reader():
        assert len(calls) == 192  # 96 origins * two toy model calls
        return original()

    monkeypatch.setattr(store, "validation_actuals_reader", reader)
    generated = generate_uncertainty(store, plan, FeatureSpec(), D4, D5, predictors=toy_predictors(calls))
    rows, metrics = evaluate_uncertainty(store, plan, generated)
    assert len(rows) == 432
    assert all(m["record_n"] == m["interval_n"] == 108 for m in metrics if m["horizon"] == "Overall")
    actuals = {}
    for r in rows:
        key = r["forecast_origin"], r["horizon"]
        assert actuals.setdefault(key, r["actual_price"]) == r["actual_price"]
    assert len(actuals) == 108


def test_hand_computed_pinball_coverage_width_and_interval_only_na(toy):
    assert pinball(120, 100, .1) == 2
    assert pinball(80, 100, .9) == pytest.approx(2)
    assert pinball(120, 100, .5) == 10
    plan, _, _ = toy
    p = prediction()
    corrected, _ = calibrate(p, [], plan, D5)
    expected = {("2021-06", 1)}
    rows = score_predictions([p, corrected], {("2021-06", 1): {"actual_price": 110., "unit": p.unit, "target_month": "2021-07"}}, expected)
    metrics = [r for r in summarize_uncertainty(rows, expected) if r["horizon"] == "Overall"]
    assert all(m["empirical_coverage"] == 1 and m["average_interval_width"] == 20 for m in metrics)
    assert metrics[0]["pinball_q10"] == 2
    assert metrics[1]["pinball_q10"] is None and metrics[1]["pinball_q10_n"] == 0
    with pytest.raises(ValueError):
        score_predictions([p, p], {("2021-06", 1): {"actual_price": 110., "unit": p.unit, "target_month": "2021-07"}}, expected)
    with pytest.raises(ValueError):
        score_predictions([p], {("2021-06", 1): {"actual_price": 110., "unit": p.unit, "target_month": "2021-08"}}, expected)


def test_risk_uses_last_public_reference_and_never_invents_probability(toy):
    plan, records, sample = toy
    p = prediction(sample.origin)
    risk = risk_signal(DevelopmentPriceStore(records, plan), p, D5)
    assert risk["reference_month"] == "2021-05"
    assert risk["rise_threshold_price"] == pytest.approx(1.1 * (100 + 736 / 10))
    assert risk["event_probability"] is None


def test_frozen_configuration_reloads_and_preserves_model_spec_and_split():
    root, config, d4, plan, spec = load_uncertainty_context(ROOT / "configs/scenarios/calibration.toml")
    assert d4 == D4 and config == D5 and root == ROOT
    assert plan.validation_origin_end == date(2024, 5, 1)
    assert config["minimum_calibration_samples"] == 24 and len(spec.lags) == 4
