"""Hand-calculated toy forecasts/features/scales; all tests run offline."""

import csv
from dataclasses import replace
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path

import pytest

from food_procurement_intelligence.data.availability import DevelopmentPriceStore
from food_procurement_intelligence.data.world_bank import PriceObservation, assumed_available_at
from food_procurement_intelligence.evaluation.backtesting import run_experiment, run_validation
from food_procurement_intelligence.evaluation.forecast_metrics import mean_absolute_error, seasonal_scale, summarize_metrics
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample, HoldoutLockedError, LeakageError, SplitPlan, add_months,
    decision_at, load_split_plans, months_between,
)
from food_procurement_intelligence.features.price import (
    FeatureSpec, FeatureUnavailableError, build_features, build_training_batch,
)
from food_procurement_intelligence.forecasting.seasonal_naive import ForecastUnavailableError, Prediction, predict


ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())


@pytest.fixture
def plan() -> SplitPlan:
    return SplitPlan(
        name="toy", data_start=date(2018, 1, 1), data_end=date(2023, 12, 1),
        train_target_start=date(2018, 1, 1), train_target_end=date(2020, 12, 1),
        validation_origin_start=date(2020, 12, 1), validation_origin_end=date(2021, 2, 1),
        validation_target_start=date(2021, 1, 1), validation_target_end=date(2021, 5, 1),
        bridge_start=date(2021, 6, 1), bridge_end=date(2021, 6, 1),
        holdout_target_start=date(2021, 7, 1), holdout_target_end=date(2023, 12, 1),
        selection_freeze_origin=date(2021, 6, 1), definition_boundary=date(2020, 7, 1),
        minimum_history_months=24,
    )


def toy_rows(plan: SplitPlan) -> list[PriceObservation]:
    """Fictitious linear prices; dates may mirror a real split but values do not."""
    return [PriceObservation(
        month, month.strftime("%Y-%m"), 100.0 + index, "wheat", "USD_per_metric_tonne",
        "Wheat, US HRW", "($/mt)", "TOY", f"A{index+1}", str(100.0 + index), False,
        assumed_available_at(month), "assumed_observation_month_plus_one_month_end", "TOY_NOT_WORLD_BANK",
    ) for index, month in enumerate(months_between(plan.data_start, plan.data_end))]


@pytest.fixture
def rows(plan) -> list[PriceObservation]:
    return toy_rows(plan)


def sample_at(origin: date) -> ForecastSample:
    return ForecastSample(origin, (1, 2, 3), tuple(add_months(origin, h) for h in (1, 2, 3)))


def test_hand_calculated_origin_relative_lags_and_windows(plan, rows) -> None:
    sample = sample_at(plan.validation_origin_start)
    vectors = build_features(DevelopmentPriceStore(rows, plan), sample, FeatureSpec())
    first = vectors[0]
    assert {key: first.values[key] for key in ("lag_1", "lag_3", "lag_6", "lag_12")} == {
        "lag_1": 134, "lag_3": 132, "lag_6": 129, "lag_12": 123,
    }
    assert first.values["rolling_mean_3"] == 133
    assert first.values["rolling_std_3"] == 1
    assert first.values["rolling_mean_12"] == 128.5
    assert first.values["rolling_std_12"] == pytest.approx(math.sqrt(13))
    assert first.values["monthly_change_fraction"] == pytest.approx(134 / 133 - 1)
    assert first.values["yearly_change_fraction"] == pytest.approx(134 / 122 - 1)
    assert [vector.values["target_calendar_month"] for vector in vectors] == [1, 2, 3]
    assert [vector.values["forecast_horizon"] for vector in vectors] == [1, 2, 3]
    assert all(vector.values["origin_calendar_month"] == 12 for vector in vectors)
    for vector in vectors:
        assert max(month for months in vector.observed_dependencies.values() for month in months) == date(2020, 11, 1)
        assert vector.observed_dependencies["yearly_change_fraction"] == (date(2020, 11, 1), date(2019, 11, 1))
        assert all(datetime.fromisoformat(stamp) <= decision_at(sample.origin) for stamp in vector.latest_dependency_available_at.values())


def test_lookback_shortage_and_missing_month_fail_explicitly(plan, rows) -> None:
    with pytest.raises(FeatureUnavailableError, match="lookback"):
        build_features(DevelopmentPriceStore(rows, plan), sample_at(date(2018, 12, 1)), FeatureSpec())
    missing = [replace(row, price=None, is_missing=True) if row.date == date(2020, 10, 1) else row for row in rows]
    with pytest.raises(FeatureUnavailableError):
        build_features(DevelopmentPriceStore(missing, plan), sample_at(plan.validation_origin_start), FeatureSpec())


@pytest.mark.parametrize("change", ["scaler", "imputer", "ddof", "bad_lag", "bad_window"])
def test_no_implicit_fitted_preprocessing_or_invalid_windows(change) -> None:
    with pytest.raises(ValueError):
        if change == "scaler":
            FeatureSpec(scaling="global_standardization")
        elif change == "imputer":
            FeatureSpec(missing_strategy="zero")
        elif change == "ddof":
            FeatureSpec(rolling_std_ddof=0)
        elif change == "bad_lag":
            FeatureSpec(lags=(0,))
        else:
            FeatureSpec(rolling_windows=(1,))


def test_target_specific_seasonal_naive_not_last_observed(plan, rows) -> None:
    store = DevelopmentPriceStore(rows, plan)
    predictions = predict(store, sample_at(plan.validation_origin_start))
    assert [row.predicted_price for row in predictions] == [124, 125, 126]
    assert [row.reference_month for row in predictions] == [date(2020, 1, 1), date(2020, 2, 1), date(2020, 3, 1)]
    assert all(row.predicted_price != store.history_as_of(plan.validation_origin_start)[-1].price for row in predictions)
    assert predictions == predict(store, sample_at(plan.validation_origin_start))


def test_missing_or_unpublished_seasonal_reference_is_not_substituted(plan, rows) -> None:
    with pytest.raises(ForecastUnavailableError):
        predict(DevelopmentPriceStore(rows, plan), sample_at(date(2018, 7, 1)))
    delayed = [replace(row, available_at="2021-01-01T00:00:00+00:00") if row.date == date(2020, 1, 1) else row for row in rows]
    with pytest.raises(ForecastUnavailableError):
        predict(DevelopmentPriceStore(delayed, plan), sample_at(plan.validation_origin_start))


@pytest.mark.parametrize("change", ["target", "cutoff", "unit", "nonfinite", "publication"])
def test_prediction_output_schema_is_checked(plan, rows, change) -> None:
    prediction = predict(DevelopmentPriceStore(rows, plan), sample_at(plan.validation_origin_start))[0]
    with pytest.raises(ValueError):
        if change == "target":
            replace(prediction, target_month=date(2021, 4, 1))
        elif change == "cutoff":
            replace(prediction, information_cutoff=prediction.forecast_origin)
        elif change == "unit":
            replace(prediction, unit="USD/kg")
        elif change == "nonfinite":
            replace(prediction, predicted_price=float("nan"))
        else:
            replace(prediction, reference_available_at="2022-01-01T00:00:00+00:00")


def test_future_prices_cannot_change_past_features_forecasts_or_scale(plan, rows) -> None:
    origin = plan.validation_origin_start
    future = [replace(row, price=row.price * 1e10) if row.date >= origin else row for row in rows]
    a, b = DevelopmentPriceStore(rows, plan), DevelopmentPriceStore(future, plan)
    assert build_features(a, sample_at(origin), FeatureSpec()) == build_features(b, sample_at(origin), FeatureSpec())
    assert predict(a, sample_at(origin)) == predict(b, sample_at(origin))
    assert seasonal_scale(a.history_as_of(origin), origin) == seasonal_scale(b.history_as_of(origin), origin)


def test_training_batch_only_contains_mature_labels_and_asof_features(plan, rows) -> None:
    store = DevelopmentPriceStore(rows, plan)
    candidates = tuple(sample_at(month) for month in (date(2018, 2, 1), date(2020, 6, 1), date(2020, 9, 1)))
    batch = build_training_batch(store, candidates, plan.validation_origin_start, FeatureSpec())
    assert len(batch.feature_vectors) == len(batch.target_values) == 3
    assert all(vector.forecast_origin == date(2020, 6, 1) for vector in batch.feature_vectors)
    assert all(vector.target_month <= date(2020, 11, 1) for vector in batch.feature_vectors)
    assert len(batch.excluded_samples) == 2
    assert {item["reason"] for item in batch.excluded_samples} >= {"unpublished_or_future_target"}


def test_validation_scorer_clock_and_holdout_remain_locked(plan, rows) -> None:
    store = DevelopmentPriceStore(rows, plan)
    scorer = store.validation_actuals_reader()
    sample = sample_at(plan.validation_origin_start)
    with pytest.raises(LeakageError):
        scorer.actuals_for(sample, decision_at(sample.origin))
    assert [value.price for value in scorer.actuals_for(sample, decision_at(plan.selection_freeze_origin))] == [136, 137, 138]
    with pytest.raises(HoldoutLockedError):
        scorer.actuals_for(sample_at(date(2021, 5, 1)), decision_at(plan.selection_freeze_origin))
    with pytest.raises(LeakageError):
        scorer.actuals_for(sample, datetime(2022, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(HoldoutLockedError):
        store.history_as_of(plan.selection_freeze_origin)
    assert "redacted" in repr(scorer)


def test_hand_calculated_mae_and_fold_scale(plan, rows) -> None:
    origin = plan.validation_origin_start
    store = DevelopmentPriceStore(rows, plan)
    scale = seasonal_scale(store.history_as_of(origin), origin)
    assert scale.value == 12
    assert scale.pair_count == 23
    assert scale.observed_through == date(2020, 11, 1)
    assert mean_absolute_error([-2, 4, -3]) == 3
    assert mean_absolute_error([]) is None
    with pytest.raises(ValueError):
        mean_absolute_error([float("nan")])


def test_mase_scale_rejects_future_or_unpublished_input(plan, rows) -> None:
    store = DevelopmentPriceStore(rows, plan)
    origin = plan.validation_origin_start
    history = store.history_as_of(origin)
    with pytest.raises(LeakageError):
        seasonal_scale((*history, replace(history[-1], month=origin)), origin)
    with pytest.raises(LeakageError):
        seasonal_scale((*history[:-1], replace(history[-1], available_at=datetime(2022, 1, 1, tzinfo=timezone.utc))), origin)


def test_zero_or_insufficient_scale_returns_null_not_epsilon(plan, rows) -> None:
    constant = [replace(row, price=100.0) for row in rows]
    store = DevelopmentPriceStore(constant, plan)
    zero = seasonal_scale(store.history_as_of(plan.validation_origin_start), plan.validation_origin_start)
    assert zero.value is None and zero.status == "zero_seasonal_scale"
    short = seasonal_scale(store.history_as_of(date(2018, 12, 1)), date(2018, 12, 1))
    assert short.value is None and short.status == "insufficient_seasonal_pairs"
    result = run_validation(store, plan, FeatureSpec())
    assert result.metrics["overall"]["mae"] == 0
    assert result.metrics["overall"]["mase"] is None
    assert result.metrics["overall"]["mase_undefined_n"] == 9


def test_mase_averages_fold_ratios_not_ratio_of_pooled_means() -> None:
    rows = [
        {"forecast_origin": "2020-01", "horizon": 1, "error": 4.0, "scaled_error": 2.0, "fixed_initial_scaled_error": 2.0},
        {"forecast_origin": "2020-02", "horizon": 1, "error": 4.0, "scaled_error": 1.0, "fixed_initial_scaled_error": 2.0},
    ]
    metrics = summarize_metrics(rows, 2)
    assert metrics["overall"]["mae"] == 4
    assert metrics["overall"]["mase"] == 1.5
    assert metrics["overall"]["mase"] != pytest.approx(4 / 3)
    with pytest.raises(ValueError, match="Duplicate"):
        summarize_metrics([rows[0], rows[0]], 2)


def test_rolling_validation_completeness_duplicate_target_is_intentional(plan, rows) -> None:
    result = run_validation(DevelopmentPriceStore(rows, plan), plan, FeatureSpec())
    assert result.metrics["complete"] and len(result.rows) == 9 and len(result.folds) == 3
    assert result.metrics["overall"]["mae"] == 12 and result.metrics["overall"]["mase"] == 1
    assert result.metrics["overall"]["mase_fixed_initial_asof"] == 1
    assert [fold["available_history_n"] for fold in result.folds] == [35, 36, 37]
    assert result.feature_vectors[-1].values["lag_1"] == result.rows[0]["actual_price"] == 136
    assert result.folds[-1]["last_mature_training_origin"] == "2020-10"
    repeated = [row for row in result.rows if row["target_month"] == "2021-03"]
    assert len(repeated) == 3
    assert len({(row["forecast_origin"], row["horizon"]) for row in repeated}) == 3
    assert len(result.feature_vectors) == 9


def test_missing_feature_fold_not_silently_dropped(plan, rows) -> None:
    missing = [replace(row, price=None, is_missing=True) if row.date == date(2020, 11, 1) else row for row in rows]
    result = run_validation(DevelopmentPriceStore(missing, plan), plan, FeatureSpec())
    assert not result.metrics["complete"]
    assert result.failures and result.metrics["missing_origin_horizon_keys"]


def test_holdout_and_bridge_values_cannot_change_validation_outputs(plan, rows) -> None:
    poisoned = [replace(row, price=1e100) if row.date > plan.validation_target_end else row for row in rows]
    original = run_validation(DevelopmentPriceStore(rows, plan), plan, FeatureSpec())
    changed = run_validation(DevelopmentPriceStore(poisoned, plan), plan, FeatureSpec())
    assert original == changed


def test_all_predictions_precede_evaluator_label_capability(plan, rows, monkeypatch) -> None:
    import food_procurement_intelligence.evaluation.backtesting as module
    store = DevelopmentPriceStore(rows, plan)
    original_predict, original_reader = module.predict, store.validation_actuals_reader
    completed_origins = []

    def record_prediction(*args):
        result = original_predict(*args)
        completed_origins.append(args[1].origin)
        return result

    def request_scorer():
        assert tuple(completed_origins) == months_between(plan.validation_origin_start, plan.validation_origin_end)
        return original_reader()

    monkeypatch.setattr(module, "predict", record_prediction)
    monkeypatch.setattr(store, "validation_actuals_reader", request_scorer)
    assert module.run_validation(store, plan, FeatureSpec()).metrics["complete"]


def test_config_driven_36_origin_108_pair_run_is_byte_reproducible(tmp_path, monkeypatch) -> None:
    import food_procurement_intelligence.evaluation.backtesting as module
    configs = tmp_path / "configs"
    configs.mkdir()
    for filename in ("forecasting/features.toml", "data/quality.toml", "evaluation/splits.toml"):
        (configs / filename).parent.mkdir(parents=True, exist_ok=True)
        (configs / filename).write_bytes((ROOT / "configs" / filename).read_bytes())
    plan, _ = load_split_plans(configs / "evaluation/splits.toml")
    store = DevelopmentPriceStore(toy_rows(plan), plan)
    monkeypatch.setattr(module, "load_development_store", lambda *_: store)
    with (configs / "data/quality.toml").open("rb") as file:
        import tomllib
        day2 = tomllib.load(file)
    # Metadata-only mock manifest; tests never read real prices or the network.
    manifest = tmp_path / day2["source_manifest"]
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "raw_snapshot_id": "TOY", "raw_sha256": "TOY", "selected_source_series": "Wheat, US HRW",
        "outputs": {"Wheat, US HRW": {"path": "TOY_NOT_REAL.csv", "sha256": "TOY", "rows": 801}},
    }), encoding="utf-8")
    first = run_experiment(configs / "forecasting/features.toml")
    second = run_experiment(configs / "forecasting/features.toml")
    assert first["complete"] and first["validation_origins"] == 36 and first["evaluated_pairs"] == 108
    assert first["overall"]["mae"] == 12 and first["overall"]["mase"] == 1
    for filename in ("validation_predictions.csv", "validation_features.csv", "feature_provenance.json", "fold_audit.csv", "metrics.json", "failures.json"):
        assert (tmp_path / first["report_dir"] / filename).read_bytes() == (tmp_path / second["report_dir"] / filename).read_bytes()
    with (tmp_path / first["report_dir"] / "validation_predictions.csv").open(encoding="utf-8", newline="") as file:
        predictions = list(csv.DictReader(file))
    assert len(predictions) == 108
    assert len({(row["forecast_origin"], row["horizon"]) for row in predictions}) == 108
    assert len({row["target_month"] for row in predictions}) == 38
    assert all("2021-07" <= row["target_month"] <= "2024-08" for row in predictions)
    assert [row["reference_month"] for row in predictions[:3]] == ["2020-07", "2020-08", "2020-09"]
