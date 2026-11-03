"""Offline checks for the Day 0 package and project entry points."""

from pathlib import Path
import tomllib

import food_procurement_intelligence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_installed_package_matches_project_metadata() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)
    assert food_procurement_intelligence.__version__ == project["project"]["version"]
    assert Path(food_procurement_intelligence.__file__).is_relative_to(
        PROJECT_ROOT / "src"
    )


def test_day0_settings_are_parseable_and_local() -> None:
    with (PROJECT_ROOT / "configs" / "day0.toml").open("rb") as file:
        settings = tomllib.load(file)
    assert settings["stage"] == "design_only"
    assert isinstance(settings["seed"], int)
    paths = [
        (PROJECT_ROOT / settings["data"][name]).resolve()
        for name in ("raw_dir", "interim_dir", "processed_dir", "synthetic_dir")
    ]
    assert len(set(paths)) == 4
    assert all(path.is_relative_to(PROJECT_ROOT) and path.is_dir() for path in paths)


def test_documentation_entry_points_exist() -> None:
    required_docs = (
        "PROJECT_CHARTER.md",
        "DATA_DICTIONARY.md",
        "DECISION_TIMELINE.md",
        "EVALUATION_PROTOCOL.md",
        "SIMULATION_ASSUMPTIONS.md",
        "ROADMAP.md",
        "DAY0_STATUS.md",
    )
    assert all((PROJECT_ROOT / "docs" / name).is_file() for name in required_docs)
