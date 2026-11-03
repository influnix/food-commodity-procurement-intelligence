"""Independent artifact arithmetic/provenance audit; never fits or scores a policy."""

import argparse
from collections import defaultdict
from datetime import datetime
import csv
import hashlib
import json
import math
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jread(path):
    return json.loads(path.read_text(encoding="utf-8"))


def cread(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def month_add(value, step):
    year, month = map(int, value.split("-"))
    index = year * 12 + month - 1 + step
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def same(left, right):
    assert math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-9), (left, right)


def moments_check(diagnostic, values):
    n = len(values)
    assert diagnostic["n"] == n
    means = [sum(row[h] for row in values) / n for h in range(3)]
    covariance = [[sum((row[i] - means[i]) * (row[k] - means[k]) for row in values) / n for k in range(3)] for i in range(3)]
    for h in range(3):
        same(means[h], diagnostic["mean"][h])
        same(covariance[h][h], diagnostic["variance"][h])
        for k in range(3):
            same(covariance[h][k], diagnostic["covariance"][h][k])
            if covariance[h][h] == 0 or covariance[k][k] == 0:
                assert diagnostic["correlation"][h][k] is None
            else:
                same(covariance[h][k] / math.sqrt(covariance[h][h] * covariance[k][k]), diagnostic["correlation"][h][k])


def verify(directory, repeat=None):
    manifest = jread(directory / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert sha(ROOT / name) == expected, name
    for name, expected in manifest["code_sha256"].items():
        assert sha(ROOT / name) == expected, name
    assert manifest["holdout_locked"] and not manifest["actual_validation_procurement_evaluated"]
    assert sha(ROOT / "configs/day6.toml") == manifest["config_sha256"]
    before = jread(ROOT / "artifacts/day6/preservation_before.json")
    assert all(sha(ROOT / name) == expected for name, expected in before["sha256"].items())
    config = manifest["config"]
    d5run = ROOT / config["day5_run"]
    assert sha(d5run / "manifest.json") == manifest["day5_manifest_sha256"]
    source = {(r["model_name"], r["forecast_origin"], int(r["horizon"])): r for r in cread(d5run / "all_oof_forecasts.csv")}
    # Reuse the guarded observation interface solely to verify already-public vector actuals.
    from food_procurement_intelligence.data.audit import load_development_store
    from food_procurement_intelligence.evaluation.splits import parse_month_label
    store = load_development_store(ROOT, ROOT / "configs/day2.toml")
    histories = {}
    pools = defaultdict(list)
    vectors = jread(directory / "joint_oof_vectors.json")
    for vector in vectors:
        origin, past, model = vector["construction_origin"], vector["source_oof_origin"], vector["source_model"]
        cutoff = month_add(origin, -1)
        assert past < origin and month_add(past, 3) <= cutoff
        if origin not in histories:
            histories[origin] = {p.month.strftime("%Y-%m"): p for p in store.history_as_of(parse_month_label(origin))}
        for i, h in enumerate((1, 2, 3)):
            raw = source[(model, past, h)]
            target = month_add(past, h)
            assert vector["target_months"][i] == target <= cutoff
            observation = histories[origin][target]
            same(vector["actual_prices"][i], observation.price)
            point = float(raw["point_prediction"])
            same(vector["point_predictions"][i], point)
            same(vector["errors"][i], observation.price - point)
            same(vector["ratios"][i], observation.price / point)
            assert vector["actual_available_at"][i] == observation.available_at.isoformat()
            clock = datetime.fromisoformat(source[(model, origin, 1)]["forecast_asof_at"])
            assert observation.available_at <= clock
            assert vector["fit_information_end"][i] < past
            assert datetime.fromisoformat(vector["fit_max_label_available_at"][i]) <= datetime.fromisoformat(raw["forecast_asof_at"])
        pools[(origin, model)].append(vector)
    assert len(pools) == 72 and {len(v) for v in pools.values()} == {59, 60}
    audits = jread(directory / "availability_audit.json")
    for audit in audits:
        pool = pools[(audit["origin"], audit["model"])]
        assert len(pool) == audit["selected"] == min(audit["eligible_before_window"], 60)
        assert len({v["source_oof_origin"] for v in pool}) == len(pool)
    rows = cread(directory / "joint_price_scenarios.csv")
    sets = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        key = row["forecast_origin"], row["source_model"], row["purpose"]
        h = int(row["horizon"])
        assert row["target_month"] == month_add(row["forecast_origin"], h) <= "2024-08"
        assert row["knowledge_type"] == "empirical_simulation_not_observed"
        assert row["information_cutoff"] == month_add(row["forecast_origin"], -1)
        assert h not in sets[key][row["scenario_id"]]
        sets[key][row["scenario_id"]][h] = row
    diagnostics = {(d["origin"], d["model"], d["purpose"]): d for d in jread(directory / "scenario_diagnostics.json")}
    assert len(rows) == 55296 and len(sets) == 144
    purpose_ids = defaultdict(set)
    additive_invalid_total = 0
    for (origin, model, purpose), paths in sets.items():
        pool = pools[(origin, model)]
        assert len(paths) == 128
        seed = int.from_bytes(hashlib.sha256(f"{config['scenarios'][purpose + '_seed']}|{origin}|{model}|{purpose}".encode()).digest()[:16], "big")
        rng = Random(seed)
        prices, ratios, additive, weights = [], [], [], []
        pool_hash = hashlib.sha256(json.dumps(pool, sort_keys=True).encode()).hexdigest()
        for index, (identifier, path) in enumerate(paths.items()):
            v = pool[rng.randrange(len(pool))]
            assert set(path) == {1, 2, 3}
            assert identifier == f"{purpose}|{model}|{origin}|{index:04d}"
            purpose_ids[purpose].add(identifier)
            values, alternative = [], []
            for h in (1, 2, 3):
                r = path[h]
                assert r["source_oof_origin"] == v["source_oof_origin"] and int(r["seed"]) == seed
                assert r["pool_sha256"] == pool_hash
                point = float(source[(model, origin, h)]["point_prediction"])
                value = float(r["price"])
                assert math.isfinite(value) and value > 0
                same(value, point * v["ratios"][h - 1])
                values.append(value)
                alternative.append(point + v["errors"][h - 1])
                same(r["probability"], 1 / 128)
            prices.append(values)
            additive.append(alternative)
            ratios.append(v["ratios"])
            weights.append(float(path[1]["probability"]))
        same(sum(weights), 1)
        diagnostic = diagnostics[(origin, model, purpose)]
        moments_check(diagnostic["price_moments"], prices)
        moments_check(diagnostic["pool_error_moments"], [v["errors"] for v in pool])
        moments_check(diagnostic["pool_ratio_moments"], [v["ratios"] for v in pool])
        moments_check(diagnostic["sampled_ratio_moments"], ratios)
        moments_check(diagnostic["additive_same_draw_moments"], additive)
        invalid = sum(any(x <= 0 or not math.isfinite(x) for x in row) for row in additive)
        assert diagnostic["additive_same_draw_invalid_paths"] == invalid
        additive_invalid_total += invalid
    assert purpose_ids["planning"].isdisjoint(purpose_ids["evaluation"])

    synthetic = ROOT / manifest["synthetic_directory"]
    supplier_data = jread(synthetic / "supplier_assumptions.json")
    suppliers = {s["supplier_id"]: s for s in supplier_data["suppliers"]}
    inputs = jread(synthetic / "toy_worlds.json")
    summaries = {r["scenario_id"]: r for r in jread(directory / "toy_cost_breakdown.json")}
    expected_inventory = {"A_normal": [120,120,120,120,120,20], "B_delay": [120,120,40,120,120,20],
        "C_demand_spike": [120,120,0,0,0,0], "D_price_rise": [120,120,120,120,120,20], "E_combined": [120,120,0,80,80,0]}
    expected_total = {"A_normal":46920, "B_delay":46680, "C_demand_spike":315960, "D_price_rise":72720, "E_combined":346320}
    for world in inputs["worlds"]:
        case = world["scenario_id"]
        assert world["knowledge_type"] == "synthetic_toy_not_world_bank"
        market = {p["month"]: p["price"] for p in world["prices"]}
        demands = dict(world["realized_demands"])
        delays = {(s, m): d for s, m, d in world["delays"]}
        orders = cread(directory / (case + "_orders.csv"))
        receipts = cread(directory / (case + "_receipts.csv"))
        ledger = cread(directory / (case + "_ledger.csv"))
        assert len(orders) == len(receipts) == len({r["order_id"] for r in receipts}) == 9
        order_map = {o["order_id"]: o for o in orders}
        capacity = defaultdict(float)
        for order in orders:
            supplier = suppliers[order["supplier_id"]]
            capacity[(order["supplier_id"], order["order_month"])] += float(order["quantity_tonnes"])
            assert order["promised_month"] == month_add(order["order_month"], supplier["lead_time_months"])
            assert month_add(order["promised_month"], supplier["maximum_delay_months"]) <= world["end"]
        assert all(q <= suppliers[s]["monthly_capacity_tonnes"] for (s, _), q in capacity.items())
        by_month = defaultdict(list)
        for receipt in receipts:
            order = order_map[receipt["order_id"]]
            supplier = suppliers[order["supplier_id"]]
            month = month_add(order["promised_month"], delays.get((order["supplier_id"], order["order_month"]), 0))
            assert receipt["receipt_month"] == month
            same(receipt["quantity_tonnes"], order["quantity_tonnes"])
            same(receipt["unit_procurement_cost"], market[month] * (1 + supplier["price_premium"]))
            same(receipt["procurement_cost"], float(receipt["unit_procurement_cost"]) * float(receipt["quantity_tonnes"]))
            by_month[month].append(receipt)
        opening = 200.
        for i, row in enumerate(ledger):
            month = row["month"]
            received = sum(float(r["quantity_tonnes"]) for r in by_month[month])
            fulfilled = min(opening + received, demands[month])
            unmet = demands[month] - fulfilled
            ending = min(opening + received - fulfilled, 400.)
            same(row["beginning_inventory"], opening)
            same(row["received_quantity"], received)
            same(row["fulfilled_demand"], fulfilled)
            same(row["unmet_demand"], unmet)
            same(row["ending_inventory"], ending)
            same(ending, expected_inventory[case][i])
            same(row["holding_cost"], ending * 3)
            same(row["unmet_cost"], unmet * 1500)
            same(row["terminal_cost"], 9 * abs(ending - 200) if i == 5 else 0)
            same(row["procurement_cost"], sum(float(r["procurement_cost"]) for r in by_month[month]))
            costs = [float(row[k]) for k in ("procurement_cost", "transport_cost", "holding_cost", "unmet_cost", "disposal_cost", "terminal_cost")]
            same(row["total_cost"], sum(costs))
            same(float(row["beginning_outstanding_quantity"]) + float(row["new_order_quantity"]), received + float(row["outstanding_quantity"]))
            assert all("actual_arrival" not in order for order in json.loads(row["outstanding_orders"]))
            opening = ending
        same(summaries[case]["total_cost"], sum(float(r["total_cost"]) for r in ledger))
        same(summaries[case]["total_cost"], expected_total[case])
        same(summaries[case]["terminal_outstanding_tonnes"], 0)
    equal = None
    if repeat:
        other = jread(repeat / "manifest.json")
        assert manifest["code_sha256"] == other["code_sha256"] and manifest["config_sha256"] == other["config_sha256"]
        names = [p.name for p in directory.iterdir() if p.is_file() and p.name not in ("manifest.json", "spec_freeze.json")]
        equal = {name: sha(directory / name) == sha(repeat / name) for name in names}
        repeat_synthetic = ROOT / other["synthetic_directory"]
        equal.update({"synthetic/" + p.name: sha(p) == sha(repeat_synthetic / p.name) for p in synthetic.iterdir() if p.is_file()})
        assert all(equal.values())
    report = {"passed":True, "run":directory.relative_to(ROOT).as_posix(), "protected_files_unchanged":len(before["sha256"]),
        "scenario_sets":len(sets), "paths":sum(len(v) for v in sets.values()), "price_rows":len(rows),
        "complete_vectors_per_pool_min":min(map(len,pools.values())), "complete_vectors_per_pool_max":max(map(len,pools.values())),
        "scenario_weight_sum":1., "invalid_multiplicative_paths":0, "additive_invalid_paths":additive_invalid_total,
        "toy_cases_verified":5, "same_origin_draws_and_moments_verified":True,
        "planning_evaluation_ids_disjoint":True, "repeated_bytes_equal":equal,
        "holdout_or_actual_validation_procurement_evaluated":False}
    output = ROOT / "artifacts/day6" / ("verification_" + directory.name + ("_repeat" if repeat else "") + ".json")
    with output.open("x",encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--repeat", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.run.resolve(), args.repeat.resolve() if args.repeat else None), indent=2))
