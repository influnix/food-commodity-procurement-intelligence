"""Named product specifications; historical numbering is compatibility metadata only."""
from pathlib import Path
import tomllib

CONFIG_FILES = {
    'source': 'configs/data/source.toml',
    'quality': 'configs/data/quality.toml',
    'restricted_export': 'configs/data/restricted_export.toml',
    'features': 'configs/forecasting/features.toml',
    'models': 'configs/forecasting/models.toml',
    'calibration': 'configs/scenarios/calibration.toml',
    'joint_and_operations': 'configs/scenarios/joint_and_operations.toml',
    'lifecycle': 'configs/scenarios/lifecycle.toml',
    'deterministic': 'configs/procurement/deterministic.toml',
    'risk': 'configs/procurement/risk.toml',
    'splits': 'configs/evaluation/splits.toml',
    'validation': 'configs/evaluation/validation.toml',
    'sensitivity': 'configs/evaluation/sensitivity.toml',
    'final': 'configs/evaluation/final.toml',
    'native_synthetic': 'configs/evaluation/native_synthetic.toml',
    'handoff': 'configs/evaluation/handoff.toml',
}


def load_spec(name: str, root: Path) -> dict:
    """Read a named TOML specification, without loading observations or artifacts."""
    return tomllib.loads((root / CONFIG_FILES[name]).read_text(encoding='utf-8'))


def historical_config_path(number: int) -> str:
    """Resolve an archived experiment identity; not a source permission or CLI."""
    names = {0: 'configs/compatibility/initial_proposal.toml',
             1: 'source', 2: 'quality', 3: 'features', 4: 'models', 5: 'calibration',
             6: 'joint_and_operations', 7: 'deterministic', 8: 'risk', 9: 'validation',
             10: 'sensitivity', 11: 'final', 12: 'native_synthetic', 15: 'lifecycle',
             16: 'handoff', 17: 'restricted_export'}
    value = names[number]
    return value if number == 0 else CONFIG_FILES[value]
