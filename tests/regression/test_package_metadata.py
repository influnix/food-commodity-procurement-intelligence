"""Offline checks for the Day 0 package and project entry points."""

from pathlib import Path
import tomllib

import food_procurement_intelligence


PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())


def test_installed_package_matches_project_metadata() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)
    assert food_procurement_intelligence.__version__ == project["project"]["version"]
    assert Path(food_procurement_intelligence.__file__).is_relative_to(
        PROJECT_ROOT / "src"
    )


def test_initial_proposal_is_parseable_and_local() -> None:
    with (PROJECT_ROOT / "configs" / "compatibility/initial_proposal.toml").open("rb") as file:
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
        "PRODUCT_OVERVIEW.md",
        "SYSTEM_ARCHITECTURE.md",
        "DATA_AND_ASOF_CONTRACT.md",
        "FORECASTING_METHOD.md",
        "UNCERTAINTY_AND_SCENARIOS.md",
        "PROCUREMENT_OPTIMIZATION.md",
        "VALIDATION_RESULTS.md",
        "REPRODUCIBILITY.md",
        "LIMITATIONS_AND_FUTURE_WORK.md",
    )
    assert all((PROJECT_ROOT / "docs" / name).is_file() for name in required_docs)
