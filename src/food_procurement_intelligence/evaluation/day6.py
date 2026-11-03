"""Day 6 saved-OOF scenario diagnostics and synthetic-only Fixed ledgers."""

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import csv
import json
from pathlib import Path
from random import Random
import sys
import tomllib

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.evaluation.model_backtesting import digest, save_csv, save_json
from food_procurement_intelligence.evaluation.splits import load_split_plans, months_between
from food_procurement_intelligence.uncertainty.joint_scenarios import SavedOOFForecasts, derived_seed, generate_joint_scenarios
from food_procurement_intelligence.simulation.engine import run_simulation
from food_procurement_intelligence.simulation.toy import HAND_EXPECTED, toy_inputs
from food_procurement_intelligence.policies.fixed import FixedProcurement


def _serializable(value):
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serializable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    return value


def load_day6(path: Path):
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    root = (path.resolve().parent / config["project_root"]).resolve()
    for key in ("day5_run", "day5_config", "report_root", "synthetic_root"):
        if not (root / config[key]).resolve().is_relative_to(root):
            raise ValueError("Day 6 path escapes project")
    if config["holdout_locked"] is not True or config["schema_version"] != 1:
        raise ValueError("Day 6 cannot unlock holdout")
    if (config["simulation"]["knowledge_type"] != "synthetic_toy_not_world_bank"
            or config["simulation"]["unit_quantity"] != "metric_tonne"
            or config["simulation"]["unit_price"] != "USD_per_metric_tonne"):
        raise ValueError("Day 6 simulation data must remain explicitly synthetic with verified units")
    for key, filename in (("day5_manifest_sha256", root / config["day5_run"] / "manifest.json"),
                          ("day5_config_sha256", root / config["day5_config"])):
        if digest(filename) != config[key]:
            raise ValueError("Frozen Day 5 input changed")
    d5 = tomllib.loads((root / config["day5_config"]).read_text(encoding="utf-8"))
    d4 = tomllib.loads((root / d5["day4_config"]).read_text(encoding="utf-8"))
    if digest(root / d5["day4_config"]) != d5["day4_config_sha256"] or digest(root / d4["split_config"]) != d4["split_config_sha256"]:
        raise ValueError("Existing model/split changed")
    sc = config["scenarios"]
    if (sc["planning_seed"] == sc["evaluation_seed"] or sc["method"] != "multiplicative_joint_oof"
            or sc["scenario_count"] != 128 or sc["pool_window"] != 60 or sc["minimum_joint_vectors"] != 24
            or sc["fallback"] != "fail_no_clipping_no_resampling"):
        raise ValueError("Keep the Day 6 initial scenario specification and distinct purpose seeds")
    plan, _ = load_split_plans(root / d4["split_config"])
    manifest = json.loads((root / config["day5_run"] / "manifest.json").read_text(encoding="utf-8"))
    package = root / "src/food_procurement_intelligence"
    for name, expected in manifest["output_sha256"].items():
        if digest(root / config["day5_run"] / name) != expected:
            raise ValueError("Day 5 artifact hash mismatch")
    for name, expected in manifest["code_sha256"].items():
        if digest(package / name) != expected:
            raise ValueError("Existing uncertainty implementation changed")
    with (root / config["day5_run"] / "all_oof_forecasts.csv").open(encoding="utf-8", newline="") as file:
        source = SavedOOFForecasts(list(csv.DictReader(file)), plan)
    return root, config, d4, plan, source, manifest


def run_day6(path: Path) -> dict:
    root, config, d4, plan, source, d5manifest = load_day6(path)
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / config["report_root"] / identifier
    synthetic = root / config["synthetic_root"] / identifier
    directory.mkdir(parents=True, exist_ok=False)
    synthetic.mkdir(parents=True, exist_ok=False)
    save_json(directory / "spec_freeze.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config, "config_sha256": digest(path), "generation_started": False})
    store = load_development_store(root, root / d4["day2_config"])
    scenario_rows, vector_rows, diagnostics, audits = [], [], [], []
    for origin in months_between(plan.validation_origin_start, plan.validation_origin_end):
        for model in config["models"]:
            points = source.points_at(origin, model)
            vectors, audit = source.vectors_as_of(store, origin, model, config["scenarios"]["pool_window"])
            audits.append({"origin": origin.strftime("%Y-%m"), "model": model, **audit})
            vector_rows.extend(v.record(origin) for v in vectors)
            for purpose in ("planning", "evaluation"):
                seed = derived_seed(config["scenarios"][purpose + "_seed"], origin, model, purpose)
                bundle, diagnostic = generate_joint_scenarios(vectors, points, origin, model, purpose,
                    config["scenarios"], plan, Random(seed), seed)
                scenario_rows.extend(bundle.records())
                diagnostics.append(diagnostic)
    save_csv(directory / "joint_price_scenarios.csv", scenario_rows)
    save_json(directory / "joint_oof_vectors.json", vector_rows)
    save_json(directory / "availability_audit.json", audits)
    save_json(directory / "scenario_diagnostics.json", diagnostics)
    settings, suppliers, initial, worlds = toy_inputs(config)
    save_json(synthetic / "supplier_assumptions.json", {"knowledge_type": config["simulation"]["knowledge_type"],
        "config_version": config["simulation"]["version"], "settings": asdict(settings), "suppliers": [asdict(s) for s in suppliers],
        "quantity_unit": "metric_tonne", "price_unit": "USD_per_metric_tonne", "initial_pipeline_is_toy_only": True})
    save_json(synthetic / "toy_worlds.json", _serializable({"initial_pipeline": [asdict(o) for o in initial], "worlds": [asdict(w) for w in worlds]}))
    policy = FixedProcurement((("A", config["simulation"]["fixed_a_tonnes"]), ("B", config["simulation"]["fixed_b_tonnes"])))
    summaries = []
    for world in worlds:
        result = run_simulation(world, settings, suppliers, policy, initial)
        save_csv(directory / (world.scenario_id + "_ledger.csv"), _serializable(result["ledger"]))
        save_csv(directory / (world.scenario_id + "_orders.csv"), _serializable(result["orders"]))
        save_csv(directory / (world.scenario_id + "_receipts.csv"), _serializable(result["receipts"]))
        summaries.append(result["summary"])
    save_json(directory / "toy_cost_breakdown.json", summaries)
    save_json(directory / "hand_calculation_expectations.json", HAND_EXPECTED)
    files = [p for folder in (directory, synthetic) for p in folder.iterdir() if p.is_file()]
    sources = [root / "src/food_procurement_intelligence/uncertainty/joint_scenarios.py", Path(__file__)]
    sources += list((root / "src/food_procurement_intelligence/simulation").glob("*.py"))
    sources += list((root / "src/food_procurement_intelligence/policies").glob("*.py"))
    save_json(directory / "manifest.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": config,
        "config_sha256": digest(path), "day5_manifest_sha256": config["day5_manifest_sha256"],
        "day5_oof_forecast_sha256": digest(root / config["day5_run"] / "all_oof_forecasts.csv"),
        "source_data": d5manifest["source_data"], "raw_sha256": d5manifest["raw_sha256"],
        "split_sha256": digest(root / d4["split_config"]), "python": sys.version,
        "rng": config["scenarios"]["rng"], "code_sha256": {p.relative_to(root).as_posix(): digest(p) for p in sources},
        "output_sha256": {p.relative_to(root).as_posix(): digest(p) for p in sorted(files)},
        "synthetic_directory": synthetic.relative_to(root).as_posix(), "holdout_locked": True,
        "actual_validation_procurement_evaluated": False, "vintage_mode": "latest_vintage_pseudo_real_time",
        "interpretation": "empirical same-pool bootstrap; separate seeds are not independent/OOS evidence"})
    return {"report_dir": directory.relative_to(root).as_posix(), "scenario_sets": len(diagnostics),
            "price_rows": len(scenario_rows), "pool_min": min(a["selected"] for a in audits),
            "pool_max": max(a["selected"] for a in audits), "toy_summaries": summaries}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/day6.toml"))
    args = parser.parse_args()
    print(json.dumps(run_day6(args.config), indent=2))
