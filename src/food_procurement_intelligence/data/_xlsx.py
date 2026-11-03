"""Read literal OOXML cells without an Excel engine or modifying the workbook.

This is intentionally a narrow reader for the inspected Pink Sheet workbook,
not a general Excel engine. Formulas, booleans and unsupported OOXML types fail
closed; numeric strings are converted by the domain parser, not by formatting.
"""

from dataclasses import dataclass
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN}


class SchemaError(ValueError):
    """The source no longer matches the explicitly reviewed contract."""


@dataclass
class LiteralWorkbook:
    sheets: dict[str, dict[str, str | None]]
    states: dict[str, str]
    core_properties: dict[str, str | None]


def read_workbook(path: Path) -> LiteralWorkbook:
    """Resolve sheet relationships and literal cell values in a local XLSX."""
    with ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 100_000_000:
            raise SchemaError("Uncompressed workbook exceeds the 100 MB limit")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(f"{{{MAIN}}}t"))
                for item in root
            ]
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib["Id"]: item
            for item in relations.findall(f"{{{PKG_REL}}}Relationship")
        }
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets: dict[str, dict[str, str | None]] = {}
        states: dict[str, str] = {}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            name = sheet.attrib["name"]
            if name in sheets:
                raise SchemaError(f"Duplicate sheet name: {name}")
            relation = targets[sheet.attrib[f"{{{REL}}}id"]]
            if relation.get("TargetMode") == "External":
                raise SchemaError("External sheet relationships are unsupported")
            target = relation.attrib["Target"]
            member = (
                target.lstrip("/") if target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", target))
            )
            if not member.startswith("xl/"):
                raise SchemaError(f"Unexpected sheet relationship: {target}")
            cells: dict[str, str | None] = {}
            root = ET.fromstring(archive.read(member))
            for cell in root.findall("m:sheetData/m:row/m:c", NS):
                address = cell.attrib["r"]
                if not re.fullmatch(r"[A-Z]+[1-9][0-9]*", address):
                    raise SchemaError(f"Invalid cell reference: {address}")
                if address in cells:
                    raise SchemaError(f"Duplicate cell {name}!{address}")
                if cell.find("m:f", NS) is not None:
                    raise SchemaError(f"Formula requires explicit review: {name}!{address}")
                value = cell.find("m:v", NS)
                text = None if value is None else value.text
                cell_type = cell.get("t", "n")
                if cell_type == "s" and text is not None:
                    index = int(text)
                    if not 0 <= index < len(shared):
                        raise SchemaError(f"Invalid shared string index: {index}")
                    text = shared[index]
                elif cell_type == "inlineStr":
                    text = "".join(
                        node.text or "" for node in cell.findall("m:is//m:t", NS)
                    )
                elif cell_type not in {"n", "s", "e"}:
                    raise SchemaError(f"Unsupported cell type {cell_type}: {name}!{address}")
                # Excel errors remain literal strings; the price parser rejects them.
                cells[address] = text
            sheets[name] = cells
            states[name] = sheet.get("state", "visible")
        properties: dict[str, str | None] = {}
        if "docProps/core.xml" in archive.namelist():
            for element in ET.fromstring(archive.read("docProps/core.xml")):
                properties[element.tag.split("}")[-1]] = element.text
    return LiteralWorkbook(sheets, states, properties)
