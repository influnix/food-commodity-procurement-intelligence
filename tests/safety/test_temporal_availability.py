"""Toy calendar/value tests; no World Bank prices, files, models or network."""

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
import json

import pytest

from food_procurement_intelligence.data.audit import audit_records
from food_procurement_intelligence.data.availability import DevelopmentPriceStore, assert_feature_available
from food_procurement_intelligence.data.world_bank import PriceObservation, assumed_available_at
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample, HoldoutLockedError, LeakageError, SplitPlan, add_months,
    assert_no_target_overlap, assert_training_available, decision_at,
    eligible_training_samples, forecast_samples, load_split_plans, months_between,
    parse_month_label, sample_metadata, samples_in_partition, summarize_plan,
)


ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())


@pytest.fixture
def plan() -> SplitPlan:
    return SplitPlan(
        name="toy", data_start=date(2020, 1, 1), data_end=date(2022, 12, 1),
        train_target_start=date(2020, 1, 1), train_target_end=date(2020, 12, 1),
        validation_origin_start=date(2020, 12, 1), validation_origin_end=date(2021, 2, 1),
        validation_target_start=date(2021, 1, 1), validation_target_end=date(2021, 5, 1),
        bridge_start=date(2021, 6, 1), bridge_end=date(2021, 6, 1),
        holdout_target_start=date(2021, 7, 1), holdout_target_end=date(2022, 12, 1),
        selection_freeze_origin=date(2021, 6, 1), definition_boundary=date(2020, 7, 1),
        minimum_history_months=3,
    )


@pytest.fixture
def rows(plan: SplitPlan) -> list[PriceObservation]:
    return [PriceObservation(
        date=month, observation_month=month.strftime("%Y-%m"), price=100.0 + index,
        commodity="wheat", unit="USD_per_metric_tonne", source_series="Wheat, US HRW",
        source_unit="($/mt)", source_sheet="toy", source_cell=f"A{index+1}",
        raw_price=str(100.0 + index), is_missing=False,
        available_at=assumed_available_at(month),
        availability_basis="assumed_observation_month_plus_one_month_end", vintage_id="TOY_NOT_REAL",
    ) for index, month in enumerate(months_between(plan.data_start, plan.data_end))]


def test_month_arithmetic_and_leap_month_end() -> None:
    assert add_months(date(2020, 1, 1), -1) == date(2019, 12, 1)
    assert add_months(date(2019, 12, 1), 3) == date(2020, 3, 1)
    assert decision_at(date(2020, 2, 1)).isoformat() == "2020-02-29T23:59:59+00:00"
    assert parse_month_label("2020-02") == date(2020, 2, 1)
    with pytest.raises(ValueError):
        add_months(date(2020, 1, 2), 1)


def test_partition_boundary_exact_months(plan: SplitPlan) -> None:
    expected = {"2020-12": "train", "2021-01": "validation", "2021-05": "validation",
                "2021-06": "bridge", "2021-07": "holdout", "2022-12": "holdout", "2023-01": "outside"}
    assert {month: plan.target_partition(parse_month_label(month)) for month in expected} == expected


@pytest.mark.parametrize("change", ["overlap", "gap", "unpublished_selection", "unlock"])
def test_invalid_partition_or_lock_config_rejected(plan: SplitPlan, change: str) -> None:
    with pytest.raises((ValueError, HoldoutLockedError)):
        if change == "overlap":
            replace(plan, validation_target_start=plan.train_target_end)
        elif change == "gap":
            replace(plan, bridge_start=date(2021, 7, 1))
        elif change == "unpublished_selection":
            # Original Day 0 error: target reaches the month immediately before holdout.
            replace(plan, validation_origin_end=date(2021, 3, 1), validation_target_end=date(2021, 6, 1), bridge_start=date(2021, 7, 1))
        else:
            replace(plan, holdout_locked=False)


def test_origin_cutoff_and_model_steps(plan: SplitPlan) -> None:
    calendar = months_between(plan.data_start, plan.data_end)
    sample, = forecast_samples(calendar, [date(2020, 12, 1)], 3)
    assert sample.feature_cutoff == date(2020, 11, 1)
    assert sample.targets == (date(2021, 1, 1), date(2021, 2, 1), date(2021, 3, 1))
    assert [row["steps_from_latest_observation"] for row in sample_metadata(sample, plan)] == [2, 3, 4]


def test_final_months_create_only_observed_targets(plan: SplitPlan) -> None:
    calendar = months_between(plan.data_start, plan.data_end)
    origins = months_between(date(2022, 9, 1), date(2022, 12, 1))
    full = forecast_samples(calendar, origins, 3)
    partial = forecast_samples(calendar, origins, 3, complete_only=False)
    assert len(full) == 1
    assert [sample.horizons for sample in partial] == [(1, 2, 3), (1, 2), (1,)]
    assert all(target <= plan.data_end for sample in partial for target in sample.targets)


def test_missing_target_month_not_fabricated(plan: SplitPlan) -> None:
    calendar = tuple(month for month in months_between(plan.data_start, plan.data_end) if month != date(2021, 2, 1))
    assert not forecast_samples(calendar, [date(2020, 12, 1)], 3)
    sample, = forecast_samples(calendar, [date(2020, 12, 1)], 3, complete_only=False)
    assert sample.horizons == (1, 3)


def test_history_warmup_uses_t_minus_one_not_current_month(plan: SplitPlan) -> None:
    calendar = months_between(plan.data_start, plan.data_end)
    assert not forecast_samples(calendar, [date(2020, 3, 1)], 3)
    assert len(forecast_samples(calendar, [date(2020, 4, 1)], 3)) == 1


def test_multihorizon_label_maturity_boundary(plan: SplitPlan) -> None:
    calendar = months_between(plan.data_start, plan.data_end)
    samples = forecast_samples(calendar, [date(2020, 8, 1), date(2020, 9, 1)], 3)
    permitted = eligible_training_samples(samples, date(2020, 12, 1))
    assert [sample.origin for sample in permitted] == [date(2020, 8, 1)]
    assert_training_available(permitted, date(2020, 12, 1))
    with pytest.raises(LeakageError):
        assert_training_available(samples, date(2020, 12, 1))
    # The one boundary sample matures next month, so it is not discarded forever.
    assert eligible_training_samples(samples, date(2021, 1, 1)) == samples


def test_publication_timestamp_can_delay_a_calendar_eligible_label(plan: SplitPlan) -> None:
    calendar = months_between(plan.data_start, plan.data_end)
    sample, = forecast_samples(calendar, [date(2020, 8, 1)], 3)
    availability = {month: datetime.fromisoformat(assumed_available_at(month)) for month in calendar}
    availability[date(2020, 11, 1)] = datetime(2021, 1, 1, tzinfo=timezone.utc)
    assert not eligible_training_samples([sample], date(2020, 12, 1), availability)


def test_forbidden_static_overlap_and_mixed_horizon_boundary(plan: SplitPlan) -> None:
    calendar = months_between(plan.data_start, plan.data_end)
    samples = forecast_samples(calendar, calendar, 3)
    train = samples_in_partition(samples, plan, "train")
    validation = samples_in_partition(samples, plan, "validation")
    assert_no_target_overlap(train, validation)
    crossing, = [sample for sample in samples if sample.origin == date(2020, 11, 1)]
    assert crossing not in train and crossing not in validation
    with pytest.raises(LeakageError):
        assert_no_target_overlap([crossing], validation)


def test_current_fold_isolated_but_past_validation_can_mature(plan: SplitPlan) -> None:
    calendar = months_between(plan.data_start, plan.data_end)
    sample, = forecast_samples(calendar, [date(2020, 12, 1)], 3)
    assert not eligible_training_samples([sample], date(2021, 3, 1))
    assert eligible_training_samples([sample], date(2021, 4, 1)) == (sample,)
    current, = forecast_samples(calendar, [date(2021, 4, 1)], 3)
    assert_no_target_overlap([sample], [current])


def test_feature_future_and_actual_availability_guards(plan: SplitPlan, rows) -> None:
    store = DevelopmentPriceStore(rows, plan)
    history = store.history_as_of(date(2020, 12, 1))
    assert history[-1].month == date(2020, 11, 1)
    assert len(history) == 11
    with pytest.raises(LeakageError):
        store.feature(date(2020, 12, 1), date(2020, 12, 1))
    availability = {date(2020, 11, 1): datetime(2021, 1, 1, tzinfo=timezone.utc)}
    with pytest.raises(LeakageError):
        assert_feature_available([date(2020, 11, 1)], date(2020, 12, 1), availability)


def test_training_value_interface_rejects_unmatured_vector(plan: SplitPlan, rows) -> None:
    store = DevelopmentPriceStore(rows, plan)
    calendar = months_between(plan.data_start, plan.data_end)
    mature, = forecast_samples(calendar, [date(2020, 8, 1)], 3)
    immature, = forecast_samples(calendar, [date(2020, 9, 1)], 3)
    assert len(store.training_targets(mature, date(2020, 12, 1))) == 3
    with pytest.raises(LeakageError):
        store.training_targets(immature, date(2020, 12, 1))


def test_holdout_interface_refuses_values_and_origins(plan: SplitPlan, rows) -> None:
    store = DevelopmentPriceStore(rows, plan)
    assert store.calendar[-1] == plan.data_end
    assert "redacted" in repr(store)
    with pytest.raises(HoldoutLockedError):
        store.history_as_of(plan.selection_freeze_origin)
    with pytest.raises(HoldoutLockedError):
        store.feature(plan.holdout_target_start, plan.validation_origin_end)


def test_future_and_holdout_price_changes_do_not_change_past_views_or_audit(plan: SplitPlan, rows) -> None:
    poisoned = [replace(row, price=row.price * 10000) if row.date > plan.validation_target_end else row for row in rows]
    assert DevelopmentPriceStore(rows, plan).history_as_of(plan.validation_origin_end) == DevelopmentPriceStore(poisoned, plan).history_as_of(plan.validation_origin_end)
    assert audit_records(rows, plan, .20) == audit_records(poisoned, plan, .20)


def test_extreme_development_values_are_flagged_and_preserved(plan: SplitPlan, rows) -> None:
    changed = [replace(row, price=10000.0) if row.date == date(2020, 8, 1) else row for row in rows]
    result = audit_records(changed, plan, .20)
    assert result["development_monthly_change_audit"]["flagged_count"] >= 2
    assert changed[7].price == 10000.0
    assert result["development_monthly_change_audit"]["data_modifications"] == 0


def test_split_config_date_only_reproduction(tmp_path: Path) -> None:
    source = ROOT / "configs/evaluation/splits.toml"
    copied = tmp_path / "copied.toml"
    copied.write_bytes(source.read_bytes())
    selected, candidates = load_split_plans(source)
    assert load_split_plans(copied) == (selected, candidates)
    calendar = months_between(selected.data_start, selected.data_end)
    report = summarize_plan(calendar, selected)
    assert report["partitions"]["train"]["calendar_months"] == 738
    assert report["partitions"]["validation"]["complete_origins"] == 36
    assert report["partitions"]["holdout"]["complete_origins"] == 22
    assert report["holdout_partial_horizon_structure_only"]["horizon_pair_counts"] == {"1": 24, "2": 23, "3": 22}
    assert report["partitions"]["train"]["complete_origins"] == 734
    assert report["partitions"]["train"]["first_origin"] == "1960-02"
    assert report["initial_validation_fit"]["mature_complete_training_origins"] == 733
    assert report["initial_validation_fit"]["last_mature_training_origin"] == "2021-02"
    assert selected.validation_target_end == add_months(selected.selection_freeze_origin, -1)


def test_audit_runner_exports_only_safe_calendar_and_audit_metadata(plan, rows, tmp_path, monkeypatch) -> None:
    from dataclasses import asdict
    import food_procurement_intelligence.data.audit as module

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "evaluation").mkdir()
    (config_dir / "data").mkdir()
    common = {
        "schema_version": 1, "selected_candidate": "toy", "data_start": "2020-01", "data_end": "2022-12",
        "minimum_history_months": 3, "minimum_sample_history_months": 1,
        "horizons": [1, 2, 3], "publication_lag_months": 1,
        "definition_boundary": "2020-07", "holdout_locked": True,
    }
    text = "\n".join(f"{key} = {json.dumps(value)}" for key, value in common.items())
    text += '\n[[candidates]]\nname = "toy"\n'
    for key, value in asdict(plan).items():
        if key not in common and key != "name":
            text += f"{key} = {json.dumps(value.strftime('%Y-%m'))}\n"
    (config_dir / "evaluation/splits.toml").write_text(text, encoding="utf-8")
    day2 = config_dir / "data/quality.toml"
    day2.write_text(
        'schema_version = 1\nproject_root = "../.."\nsplit_config = "configs/evaluation/splits.toml"\n'
        'source_manifest = "unused_toy_manifest"\nsource_manifest_sha256 = "toy"\n'
        'report_root = "reports"\ndevelopment_absolute_monthly_change_threshold = 0.20\n'
        'holdout_price_statistics = false\n', encoding="utf-8",
    )
    # Use isolated toy records; production raw/CSV verification is not bypassed
    # in the real run, only in this test of report/holdout boundaries.
    poisoned = [replace(row, price=1e100) if row.date > plan.validation_target_end else row for row in rows]
    monkeypatch.setattr(module, "_verified_records", lambda *_: (poisoned, {"toy_integrity": True}))
    result = module.run_data_audit(day2)
    report_dir = tmp_path / result["report_dir"]
    report = json.loads((report_dir / "data_audit.json").read_text(encoding="utf-8"))
    assert report["development_monthly_change_audit"]["flagged_count"] == 0
    calendar_text = (report_dir / "sample_calendar.csv").read_text(encoding="utf-8")
    assert "2022-12" in calendar_text
    assert "price" not in calendar_text.splitlines()[0]
    assert all("1e+100" not in path.read_text(encoding="utf-8") for path in report_dir.iterdir())
    assert json.loads((report_dir / "run_manifest.json").read_text())["holdout_locked"] is True
