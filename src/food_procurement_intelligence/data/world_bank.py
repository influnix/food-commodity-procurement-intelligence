"""Offline, schema-checked extraction of the reviewed World Bank Wheat series.

Run with --config configs/day1.toml. Network access requires explicit --download;
the default only verifies and processes the pinned local snapshot.
"""

import argparse
from calendar import monthrange
from collections import Counter
import csv
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tomllib
from typing import Any

from ._xlsx import LiteralWorkbook, SchemaError, read_workbook
from .acquisition import download_monthly_snapshot


PARSER_VERSION = "1.0.0"


def parse_month(value: str) -> date:
    """Parse the observed YYYY'M'MM text format; return a month-start label."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}M(0[1-9]|1[0-2])", value):
        raise SchemaError(f"Expected a YYYYMmm month string, got {value!r}")
    try:
        return date(int(value[:4]), int(value[-2:]), 1)
    except ValueError as error:
        raise SchemaError(f"Invalid calendar month: {value!r}") from error


def parse_price(value: str | None, missing_strings: list[str]) -> float | None:
    """Preserve documented missing values; reject unknown text and invalid prices."""
    if value is None or (isinstance(value, str) and value.strip() in {"", *missing_strings}):
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", value.strip()
    ):
        raise SchemaError(f"Unexpected nonnumeric price token: {value!r}")
    price = float(value)
    if not math.isfinite(price) or price <= 0:
        raise SchemaError(f"Price must be finite and positive, got {value!r}")
    return price


def month_index(month: date) -> int:
    return month.year * 12 + month.month - 1


def validate_months(months: list[date]) -> dict[str, Any]:
    """Detect duplicates/gaps before sorting; never fabricate missing observations."""
    if not months:
        raise SchemaError("No monthly observations found")
    counts = Counter(months)
    duplicates = sorted(month.isoformat() for month, count in counts.items() if count > 1)
    if duplicates:
        raise SchemaError(f"Duplicate observation months: {duplicates}")
    ordered = sorted(months)
    observed = {month_index(month) for month in months}
    gaps = [
        f"{index // 12:04d}-{index % 12 + 1:02d}"
        for index in range(month_index(ordered[0]), month_index(ordered[-1]) + 1)
        if index not in observed
    ]
    return {"source_was_sorted": months == ordered, "missing_months": gaps, "duplicate_months": 0}


def assumed_available_at(month: date, lag_months: int = 1) -> str:
    """An explicit model assumption, NOT an observed publication timestamp."""
    if lag_months != 1:
        raise ValueError("Day 1 preserves the Day 0 one-month availability lag")
    index = month_index(month) + lag_months
    year, month_number = index // 12, index % 12 + 1
    return datetime(
        year, month_number, monthrange(year, month_number)[1], 23, 59, 59,
        tzinfo=timezone.utc,
    ).isoformat()


@dataclass
class PriceObservation:
    date: date
    observation_month: str
    price: float | None
    commodity: str
    unit: str
    source_series: str
    source_unit: str
    source_sheet: str
    source_cell: str
    raw_price: str | None
    is_missing: bool
    available_at: str
    availability_basis: str
    vintage_id: str


@dataclass
class MonthlyTable:
    workbook: LiteralWorkbook
    schema: dict[str, Any]
    dated_rows: list[tuple[int, date]]
    month_checks: dict[str, Any]


def validate_schema(workbook: LiteralWorkbook, schema: dict[str, Any]) -> MonthlyTable:
    """Check inspected sheets, headers, units, descriptions and row structure."""
    if schema.get("schema_version") != 1:
        raise SchemaError("Unsupported reviewed schema version")
    if workbook.states != schema["sheet_states"]:
        raise SchemaError(f"Sheet names/states changed: {workbook.states}")
    cells = workbook.sheets[schema["price_sheet"]]
    if cells.get(schema["title_cell"]) != schema["expected_title"]:
        raise SchemaError("Monthly Prices title changed")
    for address, expected in schema["currency_cells"].items():
        if cells.get(address) != expected:
            raise SchemaError(f"Currency/nominal-price statement changed at {address}")
    header_row, unit_row = schema["header_row"], schema["unit_row"]
    headers = {
        re.sub(r"[0-9]+$", "", address): value
        for address, value in cells.items()
        if re.fullmatch(rf"[A-Z]+{header_row}", address) and value is not None
    }
    expected_headers = {item["column"]: item["source_series"] for item in schema["expected_price_columns"]}
    if headers != expected_headers:
        raise SchemaError("Price columns changed: added, removed, renamed or shifted headers")
    if len(set(value.strip() for value in headers.values())) != len(headers):
        raise SchemaError("Duplicate normalized price headers")
    for item in schema["expected_price_columns"]:
        if cells.get(f"{item['column']}{unit_row}") != item["source_unit"]:
            raise SchemaError(f"Price unit changed for {item['source_series']}")
    wheat_headers = {name for name in headers.values() if "wheat" in name.casefold()}
    configured = {item["source_series"] for item in schema["series"]}
    if wheat_headers != configured:
        raise SchemaError("Reviewed Wheat series are not the complete observed Wheat column set")
    descriptions = workbook.sheets[schema["description_sheet"]]
    for item in schema["series"]:
        if headers.get(item["column"]) != item["source_series"]:
            raise SchemaError("Series-to-column mapping is inconsistent")
        for cell_key, expected_key in (("description_cell", "description"), ("provider_cell", "providers")):
            if descriptions.get(item[cell_key]) != item[expected_key]:
                raise SchemaError(f"Series description/provider changed for {item['source_series']}")
        # Conversion is identity only after both unit and nominal-USD text checks.
        if item["source_unit"] != "($/mt)" or item["unit"] != "USD_per_metric_tonne":
            raise SchemaError("No reviewed unit conversion for the selected Wheat series")
    for location, expected in schema.get("evidence_notes", {}).items():
        sheet, address = location.rsplit("!", 1)
        if workbook.sheets[sheet].get(address) != expected:
            raise SchemaError(f"Reviewed source note changed at {location}")
    rows: dict[int, dict[str, str]] = {}
    for address, value in cells.items():
        row_number = int(re.search(r"[0-9]+$", address).group())  # type: ignore[union-attr]
        if row_number >= schema["data_start_row"] and value is not None:
            rows.setdefault(row_number, {})[address] = value
    dated_rows: list[tuple[int, date]] = []
    for row_number in sorted(rows):
        token = rows[row_number].get(f"{schema['date_column']}{row_number}")
        if token is None:
            raise SchemaError(f"Nonempty price row {row_number} has no date")
        dated_rows.append((row_number, parse_month(token)))
    checks = validate_months([month for _, month in dated_rows])
    return MonthlyTable(workbook, schema, sorted(dated_rows, key=lambda pair: pair[1]), checks)


def extract_series(
    table: MonthlyTable, source_series: str, vintage_id: str,
    availability_basis: str = "assumed_observation_month_plus_one_month_end",
) -> list[PriceObservation]:
    matches = [item for item in table.schema["series"] if item["source_series"] == source_series]
    if len(matches) != 1:
        raise SchemaError(f"Expected one exact reviewed series: {source_series!r}")
    item = matches[0]
    cells = table.workbook.sheets[table.schema["price_sheet"]]
    records = []
    for row_number, month in table.dated_rows:
        address = f"{item['column']}{row_number}"
        raw_price = cells.get(address)
        price = parse_price(raw_price, table.schema["missing_strings"])
        records.append(PriceObservation(
            date=month, observation_month=month.strftime("%Y-%m"), price=price,
            commodity=item["commodity"], unit=item["unit"], source_series=source_series,
            source_unit=item["source_unit"], source_sheet=table.schema["price_sheet"],
            source_cell=address, raw_price=raw_price, is_missing=price is None,
            available_at=assumed_available_at(month), availability_basis=availability_basis,
            vintage_id=vintage_id,
        ))
    if all(record.price is None for record in records):
        raise SchemaError(f"No valid observations for {source_series}")
    return records


def series_quality(records: list[PriceObservation]) -> dict[str, Any]:
    valid = [record for record in records if record.price is not None]
    missing = [record for record in records if record.price is None]
    return {
        "source_series": records[0].source_series,
        "unit": records[0].unit,
        "rows": len(records), "valid_prices": len(valid), "missing_prices": len(missing),
        "calendar_start": records[0].observation_month,
        "calendar_end": records[-1].observation_month,
        "first_valid_month": valid[0].observation_month,
        "last_valid_month": valid[-1].observation_month,
        "missing_observation_months": [record.observation_month for record in missing],
        "missing_tokens": dict(Counter(record.raw_price for record in missing)),
        "numeric_type": "float (finite, strictly positive) or None",
        "imputation": "none",
    }


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_series(path: Path, records: list[PriceObservation]) -> None:
    """CSV stores a missing price as an empty field, never a zero."""
    with path.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[field.name for field in fields(PriceObservation)], lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


def run_extraction(config_path: Path, download: bool = False) -> dict[str, Any]:
    """Verify raw bytes and schema, write versioned output, never split or model."""
    config_path = config_path.resolve()
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported Day 1 config version")
    project_root = (config_path.parent / config["project_root"]).resolve()

    def local_path(value: str) -> Path:
        path = (project_root / value).resolve()
        if not path.is_relative_to(project_root):
            raise ValueError(f"Config path escapes project root: {value}")
        return path

    source, extraction = config["source"], config["extraction"]
    if extraction["price_publication_lag_months"] != 1:
        raise ValueError("Day 1 must preserve the one-month price-publication assumption")
    if download:
        path = download_monthly_snapshot(local_path(source["raw_root"]), source["download_url"])
        print(f"New raw snapshot: {path}")
        print("Review the snapshot and explicitly pin workbook/hash in a new config before extraction.")
        return {"downloaded_workbook": str(path)}
    workbook_path = local_path(source["workbook"])
    raw_manifest_path = workbook_path.parent / "manifest.json"
    raw_manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
    if digest != source["sha256"] or digest != raw_manifest["sha256"]:
        raise ValueError("Raw SHA-256 does not match pinned config and acquisition manifest")
    if workbook_path.stat().st_size != raw_manifest["size_bytes"]:
        raise ValueError("Raw file size does not match acquisition manifest")
    schema_path = local_path(source["schema"])
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    workbook = read_workbook(workbook_path)
    table = validate_schema(workbook, schema)
    all_records = {
        item["source_series"]: extract_series(table, item["source_series"], raw_manifest["vintage_id"], extraction["availability_basis"])
        for item in schema["series"]
    }
    selected = extraction["selected_source_series"]
    if selected not in all_records:
        raise SchemaError("Selected series is not in the reviewed Wheat columns")
    now = datetime.now(timezone.utc)
    run_id = f"{raw_manifest['snapshot_id']}__{now:%Y%m%dT%H%M%S%fZ}"
    processed = local_path(extraction["processed_root"]) / run_id
    reports = local_path(extraction["report_root"]) / run_id
    processed.mkdir(parents=True, exist_ok=False)
    reports.mkdir(parents=True, exist_ok=False)
    outputs = {}
    for name, records in all_records.items():
        filename = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + ".csv"
        destination = processed / filename
        write_series(destination, records)
        outputs[name] = {
            "path": destination.relative_to(project_root).as_posix(),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "rows": len(records),
        }
    inventory = {
        "sheets": [
            {"name": name, "state": workbook.states[name], "nonblank_cells": sum(value is not None for value in cells.values())}
            for name, cells in workbook.sheets.items()
        ],
        "core_properties": workbook.core_properties,
        "update_label": workbook.sheets[schema["price_sheet"]].get("A4"),
        "date_format": schema["date_format"],
        "price_series_count": len(schema["expected_price_columns"]),
        "price_columns": schema["expected_price_columns"],
        "price_table_months": len(table.dated_rows),
        "price_table_start": table.dated_rows[0][1].strftime("%Y-%m"),
        "price_table_end": table.dated_rows[-1][1].strftime("%Y-%m"),
        "reviewed_wheat_descriptions": schema["series"],
        "reviewed_evidence_notes": schema["evidence_notes"],
        "source_month_checks": table.month_checks,
    }
    quality = {name: series_quality(records) for name, records in all_records.items()}
    module_paths = [Path(__file__), Path(__file__).with_name("_xlsx.py"), Path(__file__).with_name("acquisition.py")]
    manifest = {
        "run_id": run_id, "created_at_utc": now.isoformat(),
        "raw_snapshot_id": raw_manifest["snapshot_id"], "raw_sha256": digest,
        "raw_manifest": raw_manifest_path.relative_to(project_root).as_posix(),
        "parser_version": PARSER_VERSION, "python_version": sys.version,
        "dependencies": "Python standard library only; no third-party runtime packages",
        "config": config, "schema": schema,
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "source_code_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in module_paths},
        "selected_source_series": selected, "outputs": outputs,
        "vintage_mode": extraction["vintage_mode"],
        "availability_is_assumed": True, "random_seed": None,
        "seed_note": "No stochastic processing or generated prices",
        "split_performed": False, "imputation_performed": False,
    }
    _write_json(reports / "workbook_inventory.json", inventory)
    _write_json(reports / "wheat_quality.json", quality)
    _write_json(reports / "extraction_manifest.json", manifest)
    return {
        "run_id": run_id, "selected_source_series": selected,
        "selected_csv": outputs[selected]["path"],
        "report_dir": reports.relative_to(project_root).as_posix(),
        "quality": quality, "month_checks": table.month_checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Explicit network acquisition only; creates a new raw snapshot")
    args = parser.parse_args()
    result = run_extraction(args.config, args.download)
    # Complete missing-month lists remain in the quality report, not console logs.
    if "quality" in result:
        result["quality"] = {
            name: {key: value for key, value in quality.items() if key != "missing_observation_months"}
            for name, quality in result["quality"].items()
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
