"""Independent saved-output arithmetic, leakage, preservation and repeat audit.

No model fitting, network, raw price export, or holdout scoring.
"""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import tomllib


ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def month_add(value, delta):
    year, month = map(int, value.split("-"))
    index = year * 12 + month - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def close(left, right):
    assert left is None and right is None or left is not None and right is not None and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-10), (left, right)


def verify(directory, repeat=None):
    manifest = read_json(directory / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert sha(directory / name) == expected, name
    for name, expected in manifest["code_sha256"].items():
        assert sha(ROOT / "src/food_procurement_intelligence" / name) == expected, name
    assert manifest["holdout_locked"] and manifest["no_search"] and manifest["no_early_stopping"]
    assert sha(ROOT / "configs/scenarios/calibration.toml") == manifest["config_sha256"]
    assert sha(ROOT / "configs/forecasting/models.toml") == manifest["model_config_sha256"]
    preserved = read_json(ROOT / "artifacts/day5/preservation_before.json")
    for name, expected in preserved["sha256"].items():
        assert sha(ROOT / name) == expected, "Day 0-4 changed: " + name
    d5 = tomllib.loads((ROOT / "configs/scenarios/calibration.toml").read_text(encoding="utf-8"))
    point_maps, actual_map = {}, {}
    for model, link in manifest["point_links"].items():
        old = ROOT / link["directory"]
        assert sha(old / "manifest.json") == link["manifest_sha256"]
        for row in read_csv(old / "predictions.csv"):
            key = row["forecast_origin"], int(row["horizon"])
            actual = row["target_month"], row["unit"], float(row["actual_price"])
            assert actual_map.setdefault(key, actual) == actual
            point_maps[(model, *key)] = float(row["predicted_price"])
    assert len(actual_map) == 108 and len({v[0] for v in actual_map.values()}) == 38

    native = read_csv(directory / "sarimax_native_intervals.csv")
    quantiles = read_csv(directory / "lightgbm_quantiles.csv")
    corrected = read_csv(directory / "calibrated_intervals.csv")
    raw = native + quantiles
    assert len(native) == len(quantiles) == 108 and len(corrected) == 216
    raw_map = {(r["model_name"], r["forecast_origin"], int(r["horizon"])): r for r in raw}
    all_records = raw + corrected
    seen, grouped = set(), defaultdict(list)
    for row in all_records:
        model = "sarimax" if row["uncertainty_method"].startswith("sarimax") else "lightgbm"
        origin, h = row["forecast_origin"], int(row["horizon"])
        key = row["model_name"], origin, h, row["uncertainty_method"]
        assert key not in seen
        seen.add(key)
        assert row["information_cutoff"] == month_add(origin, -1)
        assert row["target_month"] == month_add(origin, h)
        assert row["fit_information_end"] < origin
        assert datetime.fromisoformat(row["fit_max_label_available_at"]) <= datetime.fromisoformat(row["forecast_asof_at"])
        assert row["target_month"] <= "2024-08"
        target, unit, actual = actual_map[(origin, h)]
        assert (row["target_month"], row["unit"], float(row["actual_price"])) == (target, unit, actual)
        if row["point_prediction"]:
            close(float(row["point_prediction"]), point_maps[(model, origin, h)])
        if row["interval_usable"] == "True":
            lower, upper = float(row["lower_bound"]), float(row["upper_bound"])
            assert lower <= upper
            assert int(row["covered"]) == int(lower <= actual <= upper)
            close(float(row["interval_width"]), upper - lower)
        else:
            assert row["covered"] == row["interval_width"] == ""
        for q in (10, 50, 90):
            forecast = row[f"q{q}"]
            if forecast:
                error = actual - float(forecast)
                expected = max((q / 100) * error, (q / 100 - 1) * error)
                close(float(row[f"pinball_q{q}"]), expected)
            else:
                assert row[f"pinball_q{q}"] == ""
        grouped[(row["model_name"], row["uncertainty_method"])].append(row)
    metrics = read_json(directory / "metrics.json")
    for m in metrics:
        rows = [r for r in grouped[(m["model_name"], m["method"])] if m["horizon"] == "Overall" or int(r["horizon"]) == m["horizon"]]
        covered = [int(r["covered"]) for r in rows if r["covered"] != ""]
        widths = [float(r["interval_width"]) for r in rows if r["interval_width"] != ""]
        assert m["record_n"] == len(rows) and m["interval_n"] == len(covered)
        close(m["empirical_coverage"], sum(covered) / len(covered) if covered else None)
        close(m["average_interval_width"], sum(widths) / len(widths) if widths else None)
        for q in (10, 50, 90):
            vals = [float(r[f"pinball_q{q}"]) for r in rows if r[f"pinball_q{q}"] != ""]
            assert m[f"pinball_q{q}_n"] == len(vals)
            close(m[f"pinball_q{q}"], sum(vals) / len(vals) if vals else None)

    oof = read_csv(directory / "all_oof_forecasts.csv")
    forecast_map = {(r["model_name"], r["forecast_origin"], int(r["horizon"])): r for r in oof}
    assert len(forecast_map) == 576
    historical = [r for r in oof if r["phase"] == "historical_train"]
    assert len(historical) == 360 and all("2016-05" <= r["target_month"] <= "2021-06" for r in historical)
    residuals = read_csv(directory / "historical_oof_calibration.csv") + read_csv(directory / "validation_oof_calibration.csv")
    residual_map, target_duplicates = {}, defaultdict(list)
    for row in residuals:
        origin, h = row["residual_forecast_origin"], int(row["residual_horizon"])
        key = row["source_model"], origin, h
        assert key not in residual_map
        residual_map[key] = row
        prediction = forecast_map[key]
        assert row["residual_target_month"] == month_add(origin, h) == prediction["target_month"]
        assert row["fit_information_end"] < origin
        assert row["residual_target_month"] < row["first_released_at_origin"] <= "2024-05"
        assert row["residual_target_month"] <= "2024-04"
        actual, point = float(row["actual_price"]), float(prediction["point_prediction"])
        lower, upper = float(prediction["lower_bound"]), float(prediction["upper_bound"])
        close(float(row["residual_value"]), actual - point)
        close(float(row["calibration_score"]), max(lower - actual, actual - upper, 0))
        target_duplicates[(row["source_model"], row["residual_target_month"])].append(h)
    audit_rows = read_json(directory / "calibration_audit.json")
    assert len(audit_rows) == 216
    for audit in audit_rows:
        model, origin, h = audit["model_name"], audit["calibration_origin"], audit["horizon"]
        selected = [residual_map[(key[0], key[1], key[2])] for key in audit["selected_residual_keys"]]
        assert len(selected) == audit["selected_n"] <= 60
        assert all(r["source_model"] == model and int(r["residual_horizon"]) == h for r in selected)
        assert len({r["residual_target_month"] for r in selected}) == len(selected)
        eligible = [r for r in residuals if r["source_model"] == model and int(r["residual_horizon"]) == h
                    and r["first_released_at_origin"] <= origin]
        eligible.sort(key=lambda r: (r["residual_target_month"], r["residual_forecast_origin"]))
        assert selected == eligible[-60:]
        base = raw_map[(model, origin, h)]
        assert all(r["residual_forecast_origin"] < origin and r["residual_target_month"] <= month_add(origin, -1)
                   and datetime.fromisoformat(r["residual_actual_available_at"]) <= datetime.fromisoformat(base["forecast_asof_at"]) for r in selected)
        if audit["status"] == "calibrated":
            assert len(selected) >= 24
            rank = math.ceil((len(selected) + 1) * .8)
            adjustment = sorted(float(r["calibration_score"]) for r in selected)[rank - 1]
            close(audit["adjustment"], adjustment)
            item = next(r for r in corrected if r["model_name"] == model and r["forecast_origin"] == origin and int(r["horizon"]) == h)
            close(float(item["lower_bound"]), float(base["lower_bound"]) - adjustment)
            close(float(item["upper_bound"]), float(base["upper_bound"]) + adjustment)
            assert item["q10"] == item["q50"] == item["q90"] == ""
    signals = read_csv(directory / "risk_signals.csv")
    for signal in signals:
        assert signal["reference_month"] <= month_add(signal["forecast_origin"], -1)
        close(float(signal["rise_threshold_price"]), float(signal["reference_price"]) * 1.1)
        assert signal["event_probability"] == ""

    fit_events = read_json(directory / "fit_log.json")
    for event in fit_events:
        if event["model"] == "lightgbm" and "feature_origin_end" in event:
            assert event["feature_origin_end"][:7] <= month_add(event["forecast_origin"], -4)
            assert event["train_end"][:7] <= month_add(event["forecast_origin"], -1)
            assert len(event["feature_names"]) == 15
            assert event["objective"] == ("regression_l2" if event["quantile"] is None else "quantile")
            assert event["alpha"] == event["quantile"]
        if event["model"] == "sarimax":
            assert event["train_end"][:7] == month_add(event["forecast_origin"], -1)

    deterministic = ["sarimax_native_intervals.csv", "lightgbm_quantiles.csv", "calibrated_intervals.csv",
        "all_oof_forecasts.csv", "historical_oof_calibration.csv", "validation_oof_calibration.csv",
        "calibration_audit.json", "pending_oof_metadata.json", "metrics.json", "uncertainty_comparison.csv", "risk_signals.csv"]
    repeated = None
    if repeat:
        other = read_json(repeat / "manifest.json")
        assert manifest["config_sha256"] == other["config_sha256"]
        assert manifest["code_sha256"] == other["code_sha256"]
        repeated = {name: sha(directory / name) == sha(repeat / name) for name in deterministic}
        assert all(repeated.values())
    report = {"passed": True, "run": directory.relative_to(ROOT).as_posix(), "repeat": repeat.relative_to(ROOT).as_posix() if repeat else None,
        "protected_day0_to4_files": len(preserved["sha256"]), "expected_validation_keys_per_method": 108,
        "unique_validation_targets": 38, "uncertainty_records": len(all_records), "oof_forecasts": len(oof),
        "historical_oof_residuals": sum(r["phase"] == "historical_train" for r in residuals),
        "validation_mature_oof_residuals": sum(r["phase"] == "validation" for r in residuals),
        "audited_calibrations": len(audit_rows), "same_target_multi_horizon_groups": sum(len(v) > 1 for v in target_duplicates.values()),
        "repeated_bytes_equal": repeated, "holdout_access_or_scoring": False,
        "independent_arithmetic": "pinball, coverage, width, OOF scores, finite order statistic and interval adjustment"}
    destination = ROOT / "artifacts/day5" / ("verification_" + directory.name + ("_repeat" if repeat else "") + ".json")
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--repeat", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.run.resolve(), args.repeat.resolve() if args.repeat else None), indent=2))
