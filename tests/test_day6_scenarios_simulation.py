"""Offline synthetic-only joint paths and independently hand-checked Toy ledgers."""

from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path
import random
from random import Random
import tomllib

import pytest

from food_procurement_intelligence.data.availability import DevelopmentPriceStore, VisiblePrice
from food_procurement_intelligence.data.world_bank import PriceObservation, assumed_available_at
from food_procurement_intelligence.evaluation.splits import (
    add_months, decision_at, load_split_plans, months_between, LeakageError, HoldoutLockedError,
)
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.uncertainty.calibration import OOFResidual
from food_procurement_intelligence.uncertainty.joint_scenarios import (
    JointResidualVector, SavedOOFForecasts, PricePath, ScenarioSet, derived_seed, generate_joint_scenarios,
)
from food_procurement_intelligence.simulation.contracts import OrderRequest, OpeningOrder, Supplier, ToyWorld, DecisionContext
from food_procurement_intelligence.simulation.engine import run_simulation
from food_procurement_intelligence.simulation.toy import HAND_EXPECTED, toy_inputs
from food_procurement_intelligence.policies.fixed import FixedProcurement

ROOT = Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((ROOT / "configs/day6.toml").read_text(encoding="utf-8"))
MODEL = "sarimax_110_10012"


@pytest.fixture
def oof_toy():
    plan, _ = load_split_plans(ROOT / "configs/splits.toml")
    records = [PriceObservation(m, m.strftime("%Y-%m"), 100. + i / 10, "wheat", "USD_per_metric_tonne",
        "Wheat, US HRW", "($/mt)", "TOY", str(i), str(100 + i / 10), False,
        assumed_available_at(m), "assumed_toy", "TOY_NOT_REAL")
        for i, m in enumerate(months_between(plan.data_start, plan.data_end))]
    origins = months_between(date(2016, 4, 1), date(2021, 3, 1)) + months_between(plan.validation_origin_start, plan.validation_origin_end)
    rows = [{"model_name": MODEL, "forecast_origin": origin.strftime("%Y-%m"), "horizon": h,
             "target_month": add_months(origin, h).strftime("%Y-%m"), "point_prediction": str(150 + i + h),
             "fit_information_end": add_months(origin, -1).strftime("%Y-%m"),
             "fit_max_label_available_at": decision_at(origin).isoformat(), "forecast_asof_at": decision_at(origin).isoformat(),
             "unit": "USD_per_metric_tonne", "phase": "historical_train" if origin < plan.validation_origin_start else "validation",
             "uncertainty_method": "sarimax_native"}
            for i, origin in enumerate(origins) for h in (1, 2, 3)]
    return plan, records, rows


def vector(past=date(2018, 1, 1), errors=(-10., -20., -30.), release=date(2021, 6, 1)):
    residuals = tuple(OOFResidual(past, add_months(past, h), h,
        datetime.fromisoformat(assumed_available_at(add_months(past, h))), MODEL, "sarimax_native", e,
        0., 100 + e, add_months(past, -1), decision_at(past), release, "historical_train")
        for h, e in zip((1, 2, 3), errors))
    return JointResidualVector(residuals, (100., 100., 100.))


def points(origin=date(2021, 6, 1), price=100.):
    return tuple(ModelPrediction(origin, add_months(origin, -1), add_months(origin, h), h, price, MODEL) for h in (1, 2, 3))


def test_joint_alignment_requires_one_origin_model_and_all_horizons():
    v = vector()
    assert v.errors == (-10, -20, -30) and v.ratios == (.9, .8, .7)
    with pytest.raises(ValueError):
        JointResidualVector(v.residuals[:2], (100.,) * 2)
    with pytest.raises(ValueError):
        JointResidualVector(v.residuals[::-1], (100.,) * 3)
    with pytest.raises(LeakageError):
        JointResidualVector((v.residuals[0], replace(v.residuals[1], source_model="other"), v.residuals[2]), (100.,) * 3)
    with pytest.raises(LeakageError):
        JointResidualVector((v.residuals[0], vector(date(2018, 2, 1)).residuals[1], v.residuals[2]), (100.,) * 3)


def test_complete_maturity_is_stricter_than_individual_h_calibration(oof_toy):
    plan, records, rows = oof_toy
    source, store = SavedOOFForecasts(rows, plan), DevelopmentPriceStore(records, plan)
    first, audit = source.vectors_as_of(store, date(2021, 6, 1), MODEL, 60)
    assert len(first) == 59 and first[-1].origin == date(2021, 2, 1)
    second, _ = source.vectors_as_of(store, date(2021, 7, 1), MODEL, 60)
    assert len(second) == 60 and second[-1].origin == date(2021, 3, 1)
    assert audit["eligible_before_window"] == 59


def test_delayed_actual_timestamp_excludes_whole_vector(oof_toy):
    plan, records, rows = oof_toy
    changed = [replace(r, available_at=decision_at(date(2021, 8, 1)).isoformat()) if r.date == date(2021, 5, 1) else r for r in records]
    source = SavedOOFForecasts(rows, plan)
    selected, _ = source.vectors_as_of(DevelopmentPriceStore(changed, plan), date(2021, 6, 1), MODEL, 60)
    assert len(selected) == 58
    assert all(date(2021, 5, 1) not in [r.residual_target_month for r in v.residuals] for v in selected)


@pytest.mark.parametrize("field,value", [("fit_information_end", "2021-07"), ("fit_max_label_available_at", "2099-01-31T23:59:59+00:00"), ("target_month", "2099-01")])
def test_bad_oof_fit_or_target_proof_rejected(oof_toy, field, value):
    plan, _, rows = oof_toy
    bad = [dict(rows[0], **{field: value}), *rows[1:]]
    with pytest.raises((LeakageError, HoldoutLockedError)):
        SavedOOFForecasts(bad, plan)


def test_incomplete_vector_is_audited_and_holdout_forecasts_rejected(oof_toy):
    plan, records, rows = oof_toy
    source = SavedOOFForecasts(rows[1:], plan)
    selected, audit = source.vectors_as_of(DevelopmentPriceStore(records, plan), plan.validation_origin_start, MODEL, 60)
    assert len(selected) == 58 and audit["incomplete"] == 1
    with pytest.raises(HoldoutLockedError):
        source.points_at(plan.selection_freeze_origin, MODEL)
    bad = dict(rows[-1], forecast_origin="2024-09", target_month="2024-12", horizon=3)
    with pytest.raises(HoldoutLockedError):
        SavedOOFForecasts([bad], plan)


def test_joint_draw_preserves_exact_vector_dependence_and_weights(oof_toy):
    plan, _, _ = oof_toy
    pool = (vector(), vector(date(2018, 2, 1), (0., 0., 0.)), vector(date(2018, 3, 1), (10., 20., 30.)))
    config = dict(CONFIG["scenarios"], minimum_joint_vectors=1)
    result, diag = generate_joint_scenarios(pool, points(), date(2021, 6, 1), MODEL, "planning", config, plan, Random(11), 11)
    assert len(result.paths) == 128 and sum(p.weight for p in result.paths) == 1
    for path in result.paths:
        assert path.prices[1] - 100 == pytest.approx(2 * (path.prices[0] - 100))
        assert path.prices[2] - 100 == pytest.approx(3 * (path.prices[0] - 100))
    assert diag["price_moments"]["correlation"][0][2] == pytest.approx(1)


def test_multiplicative_positive_while_negative_additive_is_explicit(oof_toy):
    plan, _, _ = oof_toy
    config = dict(CONFIG["scenarios"], minimum_joint_vectors=1)
    pool = (vector(errors=(-90.,) * 3),)
    result, diag = generate_joint_scenarios(pool, points(price=5), date(2021, 6, 1), MODEL, "planning", config, plan, Random(1), 1)
    assert result.paths[0].prices == (.5, .5, .5)
    assert diag["additive_same_draw_invalid_paths"] == 128
    assert diag["price_moments"]["correlation"][0][1] is None


@pytest.mark.parametrize("values", [(-1., 2., 3.), (0., 2., 3.), (float("inf"), 2., 3.), (float("nan"), 2., 3.)])
def test_invalid_path_is_failure_without_clipping(values):
    with pytest.raises(ValueError):
        PricePath("toy", date(2018, 1, 1), values, 1.)


def test_bad_probability_sum_and_insufficient_pool_and_future_vector(oof_toy):
    plan, _, _ = oof_toy
    path = PricePath("toy", date(2018, 1, 1), (1., 2., 3.), .5)
    with pytest.raises(ValueError):
        ScenarioSet(date(2021, 6, 1), MODEL, "planning", "test", 1, (path,), "hash")
    with pytest.raises(ValueError):
        generate_joint_scenarios([vector()], points(), date(2021, 6, 1), MODEL, "planning", CONFIG["scenarios"], plan, Random(1), 1)
    future = vector(date(2021, 3, 1), release=date(2021, 7, 1))
    with pytest.raises(LeakageError):
        generate_joint_scenarios([future], points(), date(2021, 6, 1), MODEL, "planning",
                                 dict(CONFIG["scenarios"], minimum_joint_vectors=1), plan, Random(1), 1)


def test_separate_purpose_seed_ids_and_repeatability_without_global_rng(oof_toy):
    plan, records, rows = oof_toy
    origin = plan.validation_origin_start
    source = SavedOOFForecasts(rows, plan)
    pool, _ = source.vectors_as_of(DevelopmentPriceStore(records, plan), origin, MODEL, 60)
    global_state = random.getstate()
    outputs = []
    for purpose in ("planning", "evaluation", "planning"):
        seed = derived_seed(CONFIG["scenarios"][purpose + "_seed"], origin, MODEL, purpose)
        outputs.append(generate_joint_scenarios(pool, source.points_at(origin, MODEL), origin, MODEL, purpose,
            CONFIG["scenarios"], plan, Random(seed), seed)[0])
    assert outputs[0] == outputs[2] and outputs[0].seed != outputs[1].seed
    assert {p.scenario_id for p in outputs[0].paths}.isdisjoint({p.scenario_id for p in outputs[1].paths})
    assert outputs[0].for_policy(origin) == outputs[0]
    with pytest.raises(LeakageError):
        outputs[1].for_policy(origin)
    assert global_state == random.getstate()


def test_future_oof_point_and_holdout_price_changes_never_affect_earlier_paths(oof_toy):
    plan, records, rows = oof_toy
    changed = [replace(r, price=1e90) if r.date >= plan.holdout_target_start else r for r in records]
    poisoned = [dict(r, point_prediction="not_a_number") if r["forecast_origin"] > "2022-01" else r for r in rows]
    for origin in (plan.validation_origin_start, date(2022, 1, 1)):
        generated = []
        for prices_, forecasts_ in ((records, rows), (changed, poisoned)):
            source = SavedOOFForecasts(forecasts_, plan)
            pool, _ = source.vectors_as_of(DevelopmentPriceStore(prices_, plan), origin, MODEL, 60)
            generated.append(generate_joint_scenarios(pool, source.points_at(origin, MODEL), origin, MODEL, "planning",
                CONFIG["scenarios"], plan, Random(1), 1)[0])
        assert generated[0] == generated[1]


def test_holdout_changes_leave_all_36_development_scenario_sets_unchanged(oof_toy):
    plan, records, rows = oof_toy
    source = SavedOOFForecasts(rows, plan)
    changed = [replace(r, price=1e90) if r.date >= plan.holdout_target_start else r for r in records]
    stores = [DevelopmentPriceStore(values, plan) for values in (records, changed)]
    for origin in months_between(plan.validation_origin_start, plan.validation_origin_end):
        outputs = []
        for store in stores:
            pool, _ = source.vectors_as_of(store, origin, MODEL, 60)
            outputs.append(generate_joint_scenarios(pool, source.points_at(origin, MODEL), origin, MODEL, "planning",
                CONFIG["scenarios"], plan, Random(1), 1)[0])
        assert outputs[0] == outputs[1]
    origin = plan.selection_freeze_origin
    with pytest.raises(HoldoutLockedError):
        generate_joint_scenarios([vector()], points(origin), origin, MODEL, "planning",
            dict(CONFIG["scenarios"], minimum_joint_vectors=1), plan, Random(1), 1)


@pytest.fixture
def supply_toy():
    return toy_inputs(CONFIG)


@pytest.mark.parametrize("index", range(5))
def test_five_cases_match_precomputed_hand_costs(supply_toy, index):
    settings, suppliers, initial, worlds = supply_toy
    result = run_simulation(worlds[index], settings, suppliers, FixedProcurement(), initial)
    for field, expected in HAND_EXPECTED[worlds[index].scenario_id].items():
        assert result["summary"][field] == pytest.approx(expected)
    assert result["summary"]["terminal_outstanding_tonnes"] == 0
    for row in result["ledger"]:
        assert row["beginning_inventory"] + row["received_quantity"] == pytest.approx(row["fulfilled_demand"] + row["disposed_quantity"] + row["ending_inventory"])
        assert row["ending_inventory"] >= 0 and row["unmet_demand"] >= 0


def test_normal_monthly_inventory_and_single_receipt_accrual(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    result = run_simulation(worlds[0], settings, suppliers, FixedProcurement(), initial)
    assert [r["received_quantity"] for r in result["ledger"]] == [20, 100, 100, 100, 100, 0]
    assert [r["ending_inventory"] for r in result["ledger"]] == [120, 120, 120, 120, 120, 20]
    assert [r["new_order_quantity"] for r in result["ledger"]] == [100, 100, 100, 20, 0, 0]
    assert sum(r["procurement_cost"] for r in result["receipts"]) == result["summary"]["procurement_cost"]
    assert len({r["order_id"] for r in result["receipts"]}) == len(result["orders"]) == 9


def test_delay_carries_pipeline_then_receives_once_at_delivery_month_price(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    result = run_simulation(worlds[4], settings, suppliers, FixedProcurement(), initial)
    receipt = next(r for r in result["receipts"] if r["order_id"] == "2000-01|A|0")
    assert receipt["promised_month"] == date(2000, 3, 1) and receipt["receipt_month"] == date(2000, 4, 1)
    assert receipt["market_price"] == 200 and receipt["procurement_cost"] == 16320
    march = result["ledger"][2]
    delayed = next(o for o in march["outstanding_orders"] if o["order_id"] == receipt["order_id"])
    assert delayed["overdue"] and "actual_arrival" not in delayed


def test_spike_is_lost_sales_not_backlog_and_penalty_not_duplicated(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    result = run_simulation(worlds[2], settings, suppliers, FixedProcurement(), initial)
    assert [r["unmet_demand"] for r in result["ledger"]] == [0, 0, 80, 0, 0, 100]
    assert result["ledger"][3]["realized_demand"] == 100
    assert result["summary"]["unmet_cost"] == 180 * 1500


def test_aggregate_capacity_moq_multiple_and_invalid_lead(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    with pytest.raises(ValueError, match="Aggregate"):
        run_simulation(worlds[0], settings, suppliers, lambda c: (OrderRequest("A", 50.), OrderRequest("A", 50.)), initial)
    with pytest.raises(ValueError):
        replace(suppliers[0], lead_time_months=0)
    lot = replace(suppliers[0], minimum_order_quantity=10., order_multiple=5.)
    lot.validate_quantity(15)
    for q in (-1., 0., 7., 12., 85., float("nan")):
        with pytest.raises(ValueError):
            lot.validate_quantity(q)


def test_terminal_guard_and_initial_pipeline_are_not_ignored(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    with pytest.raises(ValueError, match="closed evaluation window"):
        run_simulation(worlds[0], settings, suppliers,
            lambda c: (OrderRequest("B", 20.),) if c.origin == c.simulation_end else (), initial)
    with pytest.raises(ValueError):
        run_simulation(worlds[0], settings, suppliers, FixedProcurement(),
            (OpeningOrder("late", "A", date(2000, 5, 1), 80.),))


def test_policy_context_hides_future_price_demand_delay_and_evaluation_path(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    captured = []

    def spy(context):
        captured.append(context)
        assert set(asdict(context)) == {"origin", "simulation_end", "on_hand_tonnes", "planned_demand_tonnes", "suppliers", "outstanding_orders", "published_prices"}
        assert all(p.month < context.origin and p.available_at <= decision_at(context.origin) for p in context.published_prices)
        assert all(not hasattr(o, "actual_arrival") for o in context.outstanding_orders)
        return FixedProcurement()(context)

    run_simulation(worlds[4], settings, suppliers, spy, initial)
    assert len(captured) == 6 and captured[0].published_prices[-1].month == date(1999, 12, 1)
    bad = VisiblePrice(date(2000, 1, 1), 100., "USD_per_metric_tonne", decision_at(date(2000, 1, 1)))
    with pytest.raises(LeakageError):
        replace(captured[0], published_prices=(bad,))


def test_same_external_world_ledger_repeat_and_fixed_orders_ignore_future_shocks(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    outputs = [run_simulation(w, settings, suppliers, FixedProcurement(), initial) for w in (worlds[0], worlds[0], worlds[4])]
    assert outputs[0] == outputs[1]
    assert outputs[0]["orders"] == outputs[2]["orders"]
    assert sum(r["terminal_cost"] != 0 for r in outputs[0]["ledger"]) == 1


def test_overflow_disposal_and_transport_accounting(supply_toy):
    settings, suppliers, initial, worlds = supply_toy
    s = replace(settings, warehouse_capacity_tonnes=200.)
    world = replace(worlds[0], realized_demands=tuple((m, 0.) for m, _ in worlds[0].realized_demands))
    suppliers = tuple(replace(x, unit_transport_cost=2.) for x in suppliers)
    result = run_simulation(world, s, suppliers, FixedProcurement(), initial)
    assert result["summary"]["disposal_cost"] == 420
    assert result["summary"]["transport_cost"] == 840
    assert all(r["ending_inventory"] <= 200 for r in result["ledger"])
    assert result["summary"]["total_cost"] == pytest.approx(sum(result["summary"][k] for k in
        ("procurement_cost", "transport_cost", "holding_cost", "unmet_cost", "disposal_cost", "terminal_cost")))


def test_delayed_opening_order_with_no_buffer_has_hand_checked_shortages(supply_toy):
    settings, suppliers, _, worlds = supply_toy
    settings = replace(settings, initial_inventory_tonnes=0., terminal_target_tonnes=0.)
    opening = (OpeningOrder("A_early", "A", date(1999, 11, 1), 80.),
               OpeningOrder("B_early", "B", date(1999, 12, 1), 20.))
    world = replace(worlds[0], delays=(("A", date(1999, 11, 1), 1),))
    result = run_simulation(world, settings, suppliers, lambda c: (), opening)
    assert [r["received_quantity"] for r in result["ledger"]][:2] == [20, 80]
    assert [r["unmet_demand"] for r in result["ledger"]] == [80, 20, 100, 100, 100, 100]
    assert result["summary"]["procurement_cost"] == 10320
    assert result["summary"]["unmet_cost"] == 500 * 1500
    assert result["summary"]["total_cost"] == 760320
