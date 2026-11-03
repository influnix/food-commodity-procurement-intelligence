"""Coverage-aware comparison of immutable Day 3/4 validation outputs."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from .forecast_metrics import summarize_metrics
from .model_backtesting import digest, load_context, read_baseline, save_csv, save_json


def compare_rows(models: dict[str, list[dict]], baseline_name: str) -> dict:
    baseline = models[baseline_name]
    maps = {name: {(row["forecast_origin"], row["horizon"]): row for row in rows} for name, rows in models.items()}
    if any(len(maps[name]) != len(rows) for name, rows in models.items()):
        raise ValueError("Duplicate forecast keys in a model")
    expected = set(maps[baseline_name])
    for name, rows in models.items():
        if set(maps[name]) - expected:
            raise ValueError("Model has unexpected evaluation keys")
        for row in rows:
            original = maps[baseline_name][(row["forecast_origin"], row["horizon"])]
            if any(row[field] != original[field] for field in ("actual_price", "mase_scale", "target_month", "unit")):
                raise ValueError("Models must use identical actuals, target months, scales and units")
    common = set.intersection(*(set(values) for values in maps.values()))

    def table_for(subsets: dict[str, list[dict]], scope: str, expected_keys: set) -> list[dict]:
        metrics = {name: summarize_metrics(rows, len(expected_keys)) for name, rows in subsets.items()}
        result = []
        for name in subsets:
            full = set((row["forecast_origin"], row["horizon"]) for row in subsets[name]) == expected_keys
            for horizon in (1, 2, 3, "Overall"):
                summary = metrics[name]["overall"] if horizon == "Overall" else metrics[name]["by_horizon"][str(horizon)]
                base = metrics[baseline_name]["overall"] if horizon == "Overall" else metrics[baseline_name]["by_horizon"][str(horizon)]
                n_expected = len(expected_keys) if horizon == "Overall" else sum(h == horizon for _, h in expected_keys)

                def improvement(field):
                    if not full or summary[field] is None or base[field] in (None, 0):
                        return None
                    return (base[field] - summary[field]) / base[field] * 100

                result.append({"Model": name, "Horizon": horizon, "N": summary["n"], "Expected": n_expected,
                               "MAE": summary["mae"], "MASE": summary["mase"],
                               "Failure": n_expected - summary["n"],
                               "MAE_improvement_pct": improvement("mae"), "MASE_improvement_pct": improvement("mase"),
                               "scope": scope, "full_comparable_coverage": full})
        return result
    return {
        "expected_keys": len(expected), "common_success_keys": len(common),
        "coverage": {name: {"success": len(rows), "failure": len(expected) - len(rows),
                            "failure_rate": (len(expected) - len(rows)) / len(expected) if expected else None,
                            "complete": set(maps[name]) == expected} for name, rows in models.items()},
        "model_success_table": table_for(models, "own_success_set; incomplete models not rankable", expected),
        "common_success_table": table_for({name: [values[key] for key in sorted(common)] for name, values in maps.items()},
                                          "all_model_common_success_intersection", common),
        "missing_keys": {name: [list(key) for key in sorted(expected - set(values))] for name, values in maps.items()},
        "inference_limit": "108 decisions share only 38 target months; correlated errors; no holdout or procurement inference",
    }


def read_phase(directory: Path) -> tuple[list[dict], dict, dict]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["output_sha256"].items():
        if digest(directory / filename) != expected:
            raise ValueError("Day 4 phase artifact hash changed")
    with (directory / "predictions.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    numeric = ("predicted_price", "actual_price", "error", "absolute_error", "mase_scale", "scaled_error", "fixed_initial_scale", "fixed_initial_scaled_error")
    for row in rows:
        row["horizon"] = int(row["horizon"])
        for key in numeric:
            row[key] = float(row[key]) if row[key] else None
    timing = json.loads((directory / "timing.json").read_text(encoding="utf-8"))
    return rows, manifest, timing


def run_comparison(config_path: Path, phases: list[Path]) -> dict:
    root, config, plan, spec = load_context(config_path)
    baseline, baseline_manifest = read_baseline(root / config["baseline_run"])
    models = {"seasonal_naive_12": baseline}
    timings = {"seasonal_naive_12": {"total_fit_seconds": 0.0, "note": "no fitted parameters; prediction runtime is not fitting time"}}
    inputs = {"seasonal_naive_12": {"directory": config["baseline_run"], "manifest_sha256": digest(root / config["baseline_run"] / "run_manifest.json")}}
    for directory in phases:
        rows, manifest, timing = read_phase(directory)
        if manifest["config_sha256"] != digest(config_path) or manifest["split_sha256"] != config["split_config_sha256"]:
            raise ValueError("Compared phase used different model or split specifications")
        name = config[manifest["model"]]["model_name"]
        if name in models:
            raise ValueError("Duplicate model phase")
        models[name], timings[name] = rows, timing
        inputs[name] = {"directory": str(directory), "manifest_sha256": digest(directory / "manifest.json")}
    result = compare_rows(models, "seasonal_naive_12")
    directory = root / config["report_root"] / ("comparison_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    save_csv(directory / "model_comparison.csv", result["model_success_table"])
    save_csv(directory / "common_success_comparison.csv", result["common_success_table"])
    save_json(directory / "comparison.json", result)
    save_json(directory / "timing_comparison.json", timings)
    save_json(directory / "manifest.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(), "inputs": inputs,
        "config_sha256": digest(config_path), "code_sha256": digest(Path(__file__)),
        "holdout_locked": True, "no_fallback": True,
        "output_sha256": {path.name: digest(path) for path in sorted(directory.iterdir()) if path.is_file()}})
    return {"report_dir": directory.relative_to(root).as_posix(), "coverage": result["coverage"],
            "comparison": result["model_success_table"], "timings": {name: {key: value for key, value in timing.items() if key != "origin_fit_seconds"} for name, timing in timings.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/day4.toml"))
    parser.add_argument("--phases", nargs="+", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_comparison(args.config, args.phases), indent=2))
