"""Day 2 structural integrity and development-only change audit; no models."""

import argparse
import csv
from dataclasses import asdict, fields
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import tomllib

from ._xlsx import SchemaError, read_workbook
from .availability import DevelopmentPriceStore
from .world_bank import PriceObservation, extract_series, validate_months, validate_schema
from food_procurement_intelligence.evaluation.splits import (
    SplitPlan, forecast_samples, load_split_plans, months_between, sample_metadata, summarize_plan,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local(root: Path, value: str) -> Path:
    result = (root / value).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Configuration path escapes project root")
    return result


def _verified_records(root: Path, manifest_path: Path, expected_hash: str) -> tuple[list[PriceObservation], dict]:
    """Compare all raw/CSV fields internally; no price values in logs or errors."""
    if _sha256(manifest_path) != expected_hash:
        raise ValueError("Pinned Day 1 extraction manifest hash changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = manifest["selected_source_series"]
    acquisition_path = _local(root, manifest["raw_manifest"])
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    raw_path = acquisition_path.parent / acquisition["filename"]
    raw_hash = _sha256(raw_path)
    if raw_hash != manifest["raw_sha256"] or raw_hash != acquisition["sha256"]:
        raise ValueError("Raw hash mismatch")
    if raw_path.stat().st_size != acquisition["size_bytes"]:
        raise ValueError("Raw file size changed")
    schema = manifest["schema"]
    try:
        workbook = read_workbook(raw_path)
        table = validate_schema(workbook, schema)
        records = extract_series(table, selected, acquisition["vintage_id"])
    except SchemaError:
        raise ValueError("Source structure/value validation failed; price values redacted") from None
    csv_path = _local(root, manifest["outputs"][selected]["path"])
    if _sha256(csv_path) != manifest["outputs"][selected]["sha256"]:
        raise ValueError("Processed CSV hash mismatch")
    with csv_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != [field.name for field in fields(PriceObservation)]:
            raise ValueError("Processed CSV columns changed")
        actual = list(reader)
    if len(actual) != len(records):
        raise ValueError("Raw and processed row counts differ")
    for record, row in zip(records, actual):
        expected = {key: "" if value is None else str(value) for key, value in asdict(record).items()}
        if row != expected:
            raise ValueError("Raw/processed values or provenance differ; price values redacted")
    return records, {
        "raw_sha256": raw_hash, "processed_sha256": _sha256(csv_path),
        "day1_manifest_sha256": expected_hash, "raw_processed_rows_matched": len(records),
        "raw_processed_all_fields_match": True, "snapshot_id": acquisition["snapshot_id"],
        "nominal_currency_statements_match": True, "unit_identity_conversion_verified": True,
        "reviewed_definition_and_revision_notes_match": True,
    }


def audit_records(records: list[PriceObservation], plan: SplitPlan, threshold: float) -> dict:
    """Full-calendar basic checks, but no holdout/bridge price-change statistics."""
    if not 0 < threshold < 1:
        raise ValueError("Audit change threshold must be a fixed fraction in (0,1)")
    calendar = [record.date for record in records]
    checks = validate_months(calendar)
    if checks["missing_months"] or not checks["source_was_sorted"]:
        raise ValueError("MVP calendar must be continuous and sorted; no repairs applied")
    if min(calendar) != plan.data_start or max(calendar) != plan.data_end:
        raise ValueError("Data dates disagree with frozen split dates")
    if any(record.unit != "USD_per_metric_tonne" or record.source_unit != "($/mt)" for record in records):
        raise ValueError("Price unit mismatch")
    if any(record.source_series != "Wheat, US HRW" for record in records):
        raise ValueError("MVP audit requires the selected exact HRW series")
    if any(record.price is not None and not math.isfinite(record.price) for record in records):
        raise ValueError("Nonfinite price detected; values redacted")
    missing = sum(record.price is None for record in records)
    nonpositive = sum(record.price is not None and record.price <= 0 for record in records)
    # Basic validity totals are structural; no holdout levels/returns are emitted.
    decade_counts = {}
    for record in records:
        key = str((record.date.year // 10) * 10) + "s"
        item = decade_counts.setdefault(key, {"calendar_months": 0, "valid_prices": 0})
        item["calendar_months"] += 1
        item["valid_prices"] += record.price is not None
    development = [record for record in records if record.date <= plan.validation_target_end]
    flagged = []
    boundary_change = None
    for previous, current in zip(development, development[1:]):
        if previous.price is None or current.price is None or previous.price <= 0:
            continue
        change = current.price / previous.price - 1
        if current.date == plan.definition_boundary:
            boundary_change = change
        if abs(change) >= threshold:
            flagged.append({
                "month": current.observation_month, "monthly_change_fraction": change,
                "target_partition": plan.target_partition(current.date),
                "definition_boundary_month": current.date == plan.definition_boundary,
                "action": "preserve_unmodified; flag_is_not_proof_of_error",
            })
    return {
        "whole_series_structural": {
            "start": calendar[0].strftime("%Y-%m"), "end": calendar[-1].strftime("%Y-%m"),
            "rows": len(records), "missing_prices": missing, "nonpositive_prices": nonpositive,
            "month_checks": checks, "unit": "USD_per_metric_tonne", "currency_basis": "nominal_USD",
            "coverage_by_decade_counts_only": decade_counts,
            "holdout_price_levels_or_change_statistics": "not computed or exported",
        },
        "development_monthly_change_audit": {
            "start": development[0].observation_month, "end": development[-1].observation_month,
            "fixed_absolute_change_threshold": threshold, "flagged_count": len(flagged),
            "flags": flagged, "data_modifications": 0,
        },
        "definition_boundary": {
            "month": plan.definition_boundary.strftime("%Y-%m"),
            "pre_boundary_months": sum(record.date < plan.definition_boundary for record in records),
            "post_boundary_months": sum(record.date >= plan.definition_boundary for record in records),
            "boundary_month_change_fraction_development_only": boundary_change,
            "structural_break_test_performed": False,
            "interpretation": "metadata definition change; no causal or statistical break claim",
        },
    }


def load_development_store(root: Path, day2_config_path: Path) -> DevelopmentPriceStore:
    """A price-bearing API for later validation work, with no holdout access."""
    with day2_config_path.open("rb") as file:
        config = tomllib.load(file)
    plan, _ = load_split_plans(_local(root, config["split_config"]))
    records, _ = _verified_records(root, _local(root, config["day1_manifest"]), config["day1_manifest_sha256"])
    return DevelopmentPriceStore(records, plan)


def run_day2(config_path: Path) -> dict:
    config_path = config_path.resolve()
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    if config.get("schema_version") != 1 or config["holdout_price_statistics"] is not False:
        raise ValueError("Day 2 must keep holdout price statistics disabled")
    root = (config_path.parent / config["project_root"]).resolve()
    split_path = _local(root, config["split_config"])
    plan, candidates = load_split_plans(split_path)
    # Candidate selection depends on config + calendar only, before change auditing.
    calendar = months_between(plan.data_start, plan.data_end)
    summaries = [summarize_plan(calendar, candidate) for candidate in candidates]
    now = datetime.now(timezone.utc)
    directory = _local(root, config["report_root"]) / now.strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=False)

    def save(name: str, value: object) -> None:
        with (directory / name).open("x", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, ensure_ascii=False, indent=2, default=str)
            file.write("\n")

    save("split_freeze.json", {
        "created_at_utc": now.isoformat(), "selected": asdict(plan),
        "candidates_date_metadata_only": summaries, "split_config_sha256": _sha256(split_path),
        "config_copy": config, "split_config_copy": tomllib.loads(split_path.read_text(encoding="utf-8")),
        "selection_used_prices_or_model_scores": False,
        "note": "Retrospective date-only freeze, not a historical 2024 preregistration or final model/policy lock",
    })
    records, integrity = _verified_records(root, _local(root, config["day1_manifest"]), config["day1_manifest_sha256"])
    if tuple(record.date for record in records) != calendar:
        raise ValueError("Actual calendar differs from frozen metadata calendar")
    audit = audit_records(records, plan, config["development_absolute_monthly_change_threshold"])
    if audit["whole_series_structural"]["missing_prices"] or audit["whole_series_structural"]["nonpositive_prices"]:
        raise ValueError("MVP basic validity audit failed; no imputation or deletion performed")
    samples = forecast_samples(calendar, calendar, plan.minimum_sample_history_months, complete_only=False)
    catalog = [row for sample in samples for row in sample_metadata(sample, plan)]
    with (directory / "sample_calendar.csv").open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(catalog[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(catalog)
    save("data_audit.json", {"integrity": integrity, **audit})
    package_root = Path(__file__).resolve().parents[1]
    save("run_manifest.json", {
        "created_at_utc": now.isoformat(), "stage": "day2_audit_split_only", "python_version": sys.version,
        "day2_config_sha256": _sha256(config_path), "split_config_sha256": _sha256(split_path),
        "source_code_sha256": {
            "food_procurement_intelligence/" + path.relative_to(package_root).as_posix(): _sha256(path)
            for path in (
                Path(__file__).resolve(), Path(__file__).with_name("availability.py").resolve(),
                package_root / "evaluation/splits.py",
            )
        },
        "input_integrity": integrity, "holdout_locked": True,
        "outputs": {path.name: _sha256(path) for path in sorted(directory.iterdir()) if path.is_file()},
        "dependencies": "Python standard library only", "random_split": False, "model_training": False,
        "forecast_or_holdout_scoring": False, "observations_modified": 0,
    })
    return {
        "report_dir": directory.relative_to(root).as_posix(), "selected_split": plan.name,
        "summary": next(summary for summary in summaries if summary["candidate"] == plan.name),
        "structural_checks": audit["whole_series_structural"],
        "development_flagged_months": audit["development_monthly_change_audit"]["flagged_count"],
        "definition_boundary": audit["definition_boundary"], "holdout_locked": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run_day2(args.config), ensure_ascii=False, indent=2))
