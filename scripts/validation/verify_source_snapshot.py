"""Independent read-only QA using bundled openpyxl, not a runtime dependency.

Run this script with the Codex bundled Python. The production extractor and its
pytest suite use the project venv and the standard library, without openpyxl.
"""

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
import sys

import openpyxl


def verify(manifest_path: Path, project_root: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest_path = project_root / manifest["raw_manifest"]
    acquisition = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    raw_path = raw_manifest_path.parent / acquisition["filename"]
    before = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if before != manifest["raw_sha256"]:
        raise ValueError("Raw hash mismatch before independent verification")
    workbook = openpyxl.load_workbook(raw_path, read_only=True, data_only=False)
    sheet = workbook["Monthly Prices"]
    # Read once: repeated random access to a read-only sheet would be quadratic.
    cells = {cell.coordinate: cell.value for row in sheet.iter_rows() for cell in row if cell.value is not None}
    checked = {}
    for series_name, output in manifest["outputs"].items():
        csv_path = project_root / output["path"]
        if hashlib.sha256(csv_path.read_bytes()).hexdigest() != output["sha256"]:
            raise ValueError(f"Output hash mismatch: {series_name}")
        with csv_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        if len(rows) != output["rows"]:
            raise ValueError("Output row count mismatch")
        missing = 0
        for record in rows:
            address = record["source_cell"]
            column = "".join(character for character in address if character.isalpha())
            row_number = "".join(character for character in address if character.isdigit())
            if cells[column + "5"] != series_name or cells[column + "6"] != record["source_unit"]:
                raise ValueError(f"Series/unit mismatch: {address}")
            raw_date = cells["A" + row_number]
            expected_date = datetime.strptime(raw_date, "%YM%m").date().isoformat()
            if record["date"] != expected_date:
                raise ValueError(f"Date mismatch: {address}")
            raw_value = cells.get(address)
            if raw_value is None or raw_value in ("…", "..."):
                missing += 1
                if record["price"] != "" or record["is_missing"] != "True":
                    raise ValueError(f"Missing-value mismatch: {address}")
            else:
                value = float(record["price"])
                if not math.isfinite(value) or value <= 0 or value != float(raw_value):
                    raise ValueError(f"Price mismatch: {address}")
                if record["is_missing"] != "False":
                    raise ValueError(f"Missing flag mismatch: {address}")
        checked[series_name] = {"checked_rows": len(rows), "missing_rows": missing, "all_prices_match": True}
    workbook.close()
    after = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if before != after:
        raise ValueError("Raw bytes changed during verification")
    return {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "reader": "openpyxl (independent of production OOXML parser)",
        "reader_version": openpyxl.__version__,
        "python_executable": sys.executable,
        "python_version": sys.version,
        "verification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "raw_sha256_before": before, "raw_sha256_after": after,
        "series": checked, "status": "passed",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    root = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
    result = verify(args.manifest, root)
    destination = args.manifest.parent / "independent_verification.json"
    with destination.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
