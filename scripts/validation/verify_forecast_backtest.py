"""Independently check saved validation arithmetic, as-of scales and replay hashes."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import tomllib

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.evaluation.splits import add_months, load_split_plans, parse_month_label


def verify(root: Path, reference: Path, repeat: Path, config_path: Path) -> dict:
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    plan, _ = load_split_plans(root / config["split_config"])
    store = load_development_store(root, root / config["data_config"])
    manifests = [json.loads((directory / "run_manifest.json").read_text(encoding="utf-8")) for directory in (reference, repeat)]
    same = {}
    for name, expected in manifests[0]["output_sha256"].items():
        hashes = [hashlib.sha256((directory / name).read_bytes()).hexdigest() for directory in (reference, repeat)]
        if hashes[0] != expected or hashes[1] != manifests[1]["output_sha256"][name] or hashes[0] != hashes[1]:
            raise ValueError(f"Output hash mismatch: {name}")
        same[name] = True
    if manifests[0]["config_sha256"] != manifests[1]["config_sha256"]:
        raise ValueError("Replay used a different configuration")
    if hashlib.sha256((root / config["split_config"]).read_bytes()).hexdigest() != config["split_config_sha256"]:
        raise ValueError("Frozen splits changed")
    with (reference / "validation_predictions.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    metrics = json.loads((reference / "metrics.json").read_text(encoding="utf-8"))
    cache, errors, scaled = {}, [], []
    for row in rows:
        origin, target, horizon = parse_month_label(row["forecast_origin"]), parse_month_label(row["target_month"]), int(row["horizon"])
        if target != add_months(origin, horizon) or plan.target_partition(target) != "validation":
            raise ValueError("Prediction crosses the validation calendar")
        if origin not in cache:
            values = {value.month: value.price for value in store.history_as_of(origin)}
            differences = [abs(value - values[add_months(month, -12)]) for month, value in values.items() if add_months(month, -12) in values]
            cache[origin] = (values, sum(differences) / len(differences), len(differences))
        values, scale, _ = cache[origin]
        forecast, actual = float(row["predicted_price"]), float(row["actual_price"])
        if forecast != values[add_months(target, -12)]:
            raise ValueError("Seasonal reference mismatch")
        error = actual - forecast
        if not math.isclose(error, float(row["error"]), abs_tol=1e-12):
            raise ValueError("Error-sign or numerator mismatch")
        if not math.isclose(scale, float(row["mase_scale"]), rel_tol=1e-12):
            raise ValueError("Independent as-of seasonal denominator mismatch")
        errors.append(abs(error))
        scaled.append(abs(error) / scale)
    if len(rows) != 108 or len(cache) != 36 or len({(row["forecast_origin"], row["horizon"]) for row in rows}) != 108:
        raise ValueError("108-pair / 36-origin validation completeness failed")
    if not math.isclose(sum(errors) / len(errors), metrics["overall"]["mae"], rel_tol=1e-12):
        raise ValueError("Independent MAE arithmetic mismatch")
    if not math.isclose(sum(scaled) / len(scaled), metrics["overall"]["mase"], rel_tol=1e-12):
        raise ValueError("Independent equal-pair MASE arithmetic mismatch")
    first, last = min(cache), max(cache)
    fixed_scale = cache[first][1]
    if not math.isclose(sum(errors) / len(errors) / fixed_scale, metrics["overall"]["mase_fixed_initial_asof"], rel_tol=1e-12):
        raise ValueError("Independent fixed-first-asof MASE mismatch")
    for filename in ("feature_provenance.json",):
        for item in json.loads((reference / filename).read_text(encoding="utf-8")):
            cutoff = add_months(parse_month_label(item["forecast_origin"]), -1)
            if any(parse_month_label(month) > cutoff for months in item["observed_dependencies"].values() for month in months):
                raise ValueError("Feature dependency exceeds the information cutoff")
    source = manifests[0]["selected_processed_input"]
    if hashlib.sha256((root / source["path"]).read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("Existing processed input changed")
    return {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed",
        "verification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_run": reference.name, "repeat_run": repeat.name, "identical_core_outputs": same,
        "independent_arithmetic": "sum(abs(y-yhat))/n and mean(abs(y-yhat)/sum_seasonal_difference_scale)",
        "origins": len(cache), "origin_horizon_pairs": len(rows), "holdout_evaluated": False,
        "first_fold": {"origin": first.isoformat(), "scale": cache[first][1], "seasonal_pairs": cache[first][2], "history_months": len(cache[first][0])},
        "last_fold": {"origin": last.isoformat(), "scale": cache[last][1], "seasonal_pairs": cache[last][2], "history_months": len(cache[last][0])},
        "fixed_initial_scale": fixed_scale, "input_processed_sha256_unchanged": source["sha256"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--repeat-run", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/forecasting/features.toml"))
    args = parser.parse_args()
    root = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
    report = verify(root, args.reference_run, args.repeat_run, args.config)
    destination = args.repeat_run.parent / f"verification_{args.repeat_run.name}.json"
    with destination.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, indent=2, ensure_ascii=False, allow_nan=False)
        file.write("\n")
    print(json.dumps({"report": str(destination), **report}, indent=2))
