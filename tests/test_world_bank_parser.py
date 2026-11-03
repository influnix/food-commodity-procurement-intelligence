"""Offline toy fixtures only: no downloaded prices and no network requests."""

from copy import deepcopy
import csv
from datetime import date
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from food_procurement_intelligence.data._xlsx import (
    MAIN, PKG_REL, REL, LiteralWorkbook, SchemaError, read_workbook,
)
from food_procurement_intelligence.data.acquisition import validate_official_url
from food_procurement_intelligence.data.world_bank import (
    assumed_available_at, extract_series, parse_month, parse_price,
    run_extraction, series_quality, validate_months, validate_schema, write_series,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def toy_contract() -> tuple[LiteralWorkbook, dict]:
    """Reviewed metadata, two toy months; all prices are explicitly fictitious."""
    schema = json.loads((ROOT / "configs/world_bank_monthly.schema.json").read_text(encoding="utf-8"))
    schema["expected_price_columns"] = [
        item for item in schema["expected_price_columns"] if item["column"] in {"AK", "AL"}
    ]
    sheets = {name: {} for name in schema["sheet_states"]}
    cells = sheets["Monthly Prices"]
    cells["A1"] = schema["expected_title"]
    cells.update(schema["currency_cells"])
    for item in schema["series"]:
        cells[item["column"] + "5"] = item["source_series"]
        cells[item["column"] + "6"] = item["source_unit"]
        sheets["Description"][item["description_cell"]] = item["description"]
        sheets["Description"][item["provider_cell"]] = item["providers"]
    for location, value in schema["evidence_notes"].items():
        name, address = location.rsplit("!", 1)
        sheets[name][address] = value
    cells.update({"A7": "2020M01", "A8": "2020M02", "AK7": "…", "AK8": "110", "AL7": "210", "AL8": "220"})
    return LiteralWorkbook(sheets, deepcopy(schema["sheet_states"]), {}), schema


@pytest.mark.parametrize("token,expected", [
    ("1960M01", date(1960, 1, 1)), ("2020M02", date(2020, 2, 1)),
    ("2026M09", date(2026, 9, 1)), ("1999M12", date(1999, 12, 1)),
])
def test_parse_month_exact_calendar_label(token: str, expected: date) -> None:
    assert parse_month(token) == expected


@pytest.mark.parametrize("token", ["2020M00", "2020M13", "2020M1", "2020-01", "0000M01", " 2020M01", "43831", None])
def test_reject_malformed_or_serial_dates(token: str) -> None:
    with pytest.raises(SchemaError):
        parse_month(token)


@pytest.mark.parametrize("value", [None, "", " ", "…", "...", ".."])
def test_documented_missing_is_none_not_zero(value: str | None) -> None:
    assert parse_price(value, ["…", "...", ".."]) is None


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "inf", "#N/A", "unknown", "1_000", "1,000", "1e999", True])
def test_reject_unknown_or_nonpositive_prices(value: str) -> None:
    with pytest.raises(SchemaError):
        parse_price(value, ["…", "..."])


def test_numeric_conversion_preserves_float_values() -> None:
    result = parse_price("1.25e2", ["…", "..."])
    assert isinstance(result, float)
    assert result == 125.0


def test_duplicate_months_fail_before_sorting() -> None:
    with pytest.raises(SchemaError, match="Duplicate"):
        validate_months([date(2020, 1, 1), date(2020, 1, 1)])


def test_calendar_gaps_are_reported_without_filling() -> None:
    result = validate_months([date(2020, 3, 1), date(2020, 1, 1)])
    assert result["missing_months"] == ["2020-02"]
    assert result["source_was_sorted"] is False


def test_unordered_source_is_detected_and_output_is_sorted(toy_contract) -> None:
    workbook, schema = toy_contract
    cells = workbook.sheets["Monthly Prices"]
    cells["A7"], cells["A8"] = cells["A8"], cells["A7"]
    table = validate_schema(workbook, schema)
    records = extract_series(table, "Wheat, US HRW", "toy-vintage")
    assert table.month_checks["source_was_sorted"] is False
    assert [record.date for record in records] == [date(2020, 1, 1), date(2020, 2, 1)]
    assert [record.price for record in records] == [220.0, 210.0]
    assert [record.source_cell for record in records] == ["AL8", "AL7"]


def test_extract_exact_series_and_preserve_missing(toy_contract) -> None:
    workbook, schema = toy_contract
    table = validate_schema(workbook, schema)
    hrw = extract_series(table, "Wheat, US HRW", "toy-vintage")
    srw = extract_series(table, "Wheat, US SRW", "toy-vintage")
    assert [record.price for record in hrw] == [210.0, 220.0]
    assert [record.price for record in srw] == [None, 110.0]
    assert srw[0].is_missing is True
    assert hrw[0].unit == "USD_per_metric_tonne"
    assert hrw[0].source_series == "Wheat, US HRW"
    assert hrw[0].vintage_id == "toy-vintage"
    assert hrw[0].observation_month == "2020-01"
    assert series_quality(srw)["missing_prices"] == 1
    with pytest.raises(SchemaError, match="exact reviewed"):
        extract_series(table, "Wheat", "toy-vintage")


@pytest.mark.parametrize("change", ["header", "added_header", "unit", "currency", "sheet", "description", "date", "duplicate_month", "unexpected_price"])
def test_source_drift_or_bad_values_fail_closed(toy_contract, change: str) -> None:
    workbook, schema = toy_contract
    cells = workbook.sheets["Monthly Prices"]
    if change == "header":
        cells["AL5"] = "Wheat, new definition"
    elif change == "added_header":
        cells["AM5"] = "Wheat, another series"
    elif change == "unit":
        cells["AL6"] = "($/kg)"
    elif change == "currency":
        cells["A2"] = "prices in euros"
    elif change == "sheet":
        workbook.states.pop("Description")
    elif change == "description":
        workbook.sheets["Description"]["B48"] = "changed quality definition"
    elif change == "date":
        cells["A7"] = "2020-01"
    elif change == "duplicate_month":
        cells["A8"] = cells["A7"]
    else:
        cells["AL7"] = "#N/A"
    with pytest.raises(SchemaError):
        table = validate_schema(workbook, schema)
        extract_series(table, "Wheat, US HRW", "toy-vintage")


def test_available_at_is_explicit_following_month_end() -> None:
    assert assumed_available_at(date(2020, 1, 1)) == "2020-02-29T23:59:59+00:00"
    assert assumed_available_at(date(2020, 12, 1)) == "2021-01-31T23:59:59+00:00"
    with pytest.raises(ValueError):
        assumed_available_at(date(2020, 1, 1), 0)


def test_csv_null_and_provenance_round_trip(toy_contract, tmp_path: Path) -> None:
    workbook, schema = toy_contract
    records = extract_series(validate_schema(workbook, schema), "Wheat, US SRW", "toy-vintage")
    output = tmp_path / "toy.csv"
    write_series(output, records)
    with output.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["price"] == ""
    assert rows[0]["is_missing"] == "True"
    assert rows[0]["raw_price"] == "…"
    assert rows[1]["price"] == "110.0"
    assert rows[1]["source_cell"] == "AK8"
    with pytest.raises(FileExistsError):
        write_series(output, records)


def _toy_zip(path: Path, formula: bool = False) -> None:
    """Minimal OOXML ZIP fixture; not a deliverable workbook or real data."""
    workbook = ET.Element(f"{{{MAIN}}}workbook")
    sheets = ET.SubElement(workbook, f"{{{MAIN}}}sheets")
    ET.SubElement(sheets, f"{{{MAIN}}}sheet", {"name": "toy", "sheetId": "1", f"{{{REL}}}id": "rId1"})
    relations = ET.Element(f"{{{PKG_REL}}}Relationships")
    ET.SubElement(relations, f"{{{PKG_REL}}}Relationship", {"Id": "rId1", "Target": "worksheets/custom.xml"})
    worksheet = ET.Element(f"{{{MAIN}}}worksheet")
    row = ET.SubElement(ET.SubElement(worksheet, f"{{{MAIN}}}sheetData"), f"{{{MAIN}}}row", {"r": "1"})
    shared_cell = ET.SubElement(row, f"{{{MAIN}}}c", {"r": "A1", "t": "s"})
    ET.SubElement(shared_cell, f"{{{MAIN}}}v").text = "0"
    inline = ET.SubElement(row, f"{{{MAIN}}}c", {"r": "C1", "t": "inlineStr"})
    ET.SubElement(ET.SubElement(inline, f"{{{MAIN}}}is"), f"{{{MAIN}}}t").text = "toy-inline"
    numeric = ET.SubElement(row, f"{{{MAIN}}}c", {"r": "D1"})
    ET.SubElement(numeric, f"{{{MAIN}}}v").text = "123.5"
    if formula:
        ET.SubElement(numeric, f"{{{MAIN}}}f").text = "1+2"
    strings = ET.Element(f"{{{MAIN}}}sst")
    ET.SubElement(ET.SubElement(strings, f"{{{MAIN}}}si"), f"{{{MAIN}}}t").text = "toy-shared"
    with ZipFile(path, "w") as archive:
        for member, element in {
            "xl/workbook.xml": workbook,
            "xl/_rels/workbook.xml.rels": relations,
            "xl/worksheets/custom.xml": worksheet,
            "xl/sharedStrings.xml": strings,
        }.items():
            archive.writestr(member, ET.tostring(element))


def test_literal_xlsx_relationships_shared_inline_sparse_cells(tmp_path: Path) -> None:
    path = tmp_path / "toy.xlsx"
    _toy_zip(path)
    workbook = read_workbook(path)
    assert workbook.sheets["toy"] == {"A1": "toy-shared", "C1": "toy-inline", "D1": "123.5"}
    assert workbook.states == {"toy": "visible"}


def test_formula_cells_require_explicit_review(tmp_path: Path) -> None:
    path = tmp_path / "toy_formula.xlsx"
    _toy_zip(path, formula=True)
    with pytest.raises(SchemaError, match="Formula"):
        read_workbook(path)


@pytest.mark.parametrize("url", ["http://thedocs.worldbank.org/file.xlsx", "https://example.org/file.xlsx", "https://worldbank.org.evil.org/file.xlsx"])
def test_downloader_refuses_nonofficial_endpoints_without_network(url: str) -> None:
    with pytest.raises(ValueError):
        validate_official_url(url)


def test_tampered_snapshot_rejected_before_parsing(tmp_path: Path) -> None:
    directory = tmp_path / "configs"
    directory.mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw/source.xlsx").write_bytes(b"tampered toy bytes")
    (tmp_path / "raw/manifest.json").write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")
    config = directory / "toy.toml"
    config.write_text(
        'schema_version = 1\nproject_root = ".."\n[source]\n'
        'workbook = "raw/source.xlsx"\nsha256 = "' + "0" * 64 + '"\n'
        '[extraction]\nprice_publication_lag_months = 1\n', encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SHA-256"):
        run_extraction(config)
