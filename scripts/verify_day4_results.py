"""Read-only verification of Day 4 arithmetic, hashes and baseline preservation."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from food_procurement_intelligence.evaluation.model_backtesting import digest, read_baseline
from food_procurement_intelligence.evaluation.model_comparison import read_phase, compare_rows


def verify(root: Path, phase_dirs: list[Path], comparison_dir: Path) -> dict:
    baseline_dir = root / "artifacts/day3/20261027T013028732383Z"
    baseline, baseline_manifest = read_baseline(baseline_dir)
    package = root / "src/food_procurement_intelligence"
    for name, expected in baseline_manifest["code_sha256"].items():
        if digest(package / name) != expected:
            raise ValueError("Existing Day 3 code changed")
    raw = root / "data/raw/world_bank" / baseline_manifest["raw_snapshot_id"] / "CMO-Historical-Data-Monthly.xlsx"
    if digest(raw) != baseline_manifest["raw_sha256"]:
        raise ValueError("Raw bytes changed")
    source = baseline_manifest["selected_processed_input"]
    if digest(root / source["path"]) != source["sha256"]:
        raise ValueError("Existing processed CSV changed")
    models, details = {"seasonal_naive_12": baseline}, {}
    for directory in phase_dirs:
        rows, manifest, timing = read_phase(directory)
        for name, expected in manifest["code_sha256"].items():
            if digest(package / name) != expected:
                raise ValueError("Phase code differs from current source")
        for row in rows:
            error = row["actual_price"] - row["predicted_price"]
            if not math.isclose(error, row["error"], abs_tol=1e-12) or not math.isclose(abs(error), row["absolute_error"], abs_tol=1e-12):
                raise ValueError("Incorrect error arithmetic")
            if not math.isclose(abs(error) / row["mase_scale"], row["scaled_error"], rel_tol=1e-12):
                raise ValueError("Incorrect scaled error")
        metrics = json.loads((directory / "metrics.json").read_text())
        mae = sum(abs(row["actual_price"] - row["predicted_price"]) for row in rows) / len(rows)
        mase = sum(abs(row["actual_price"] - row["predicted_price"]) / row["mase_scale"] for row in rows) / len(rows)
        if not math.isclose(mae, metrics["overall"]["mae"], rel_tol=1e-12) or not math.isclose(mase, metrics["overall"]["mase"], rel_tol=1e-12):
            raise ValueError("Incorrect aggregate metric")
        models[manifest["config"][manifest["model"]]["model_name"]] = rows
        details[directory.name] = {"n": len(rows), "independent_mae": mae, "independent_mase": mase}
    checked = compare_rows(models, "seasonal_naive_12")
    if checked["expected_keys"] != 108 or checked["common_success_keys"] != 108:
        raise ValueError("Models do not have the required shared 108 keys")
    if len({row["target_month"] for row in baseline}) != 38:
        raise ValueError("Unexpected validation target count")
    manifest = json.loads((comparison_dir / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        if digest(comparison_dir / name) != expected:
            raise ValueError("Comparison artifact hash changed")
    report = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed",
              "phase_checks": details, "same_keys_actuals_scales_units": True, "shared_keys": 108,
              "unique_target_months": 38, "Day3_code_and_artifacts_unchanged": True,
              "raw_and_processed_hashes_unchanged": True, "holdout_evaluated": False,
              "verification_code_sha256": digest(Path(__file__))}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phases", nargs="+", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = verify(root, args.phases, args.comparison)
    target = args.comparison.parent / ("verification_" + args.comparison.name + ".json")
    with target.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, indent=2)
        file.write("\n")
    print(json.dumps({"report": str(target), **report}, indent=2))
