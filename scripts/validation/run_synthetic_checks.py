"""Run existing seven-policy synthetic integration and information-boundary cases."""
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0, str(ROOT))
from scripts.ci.run_contract_tests import main

if __name__ == '__main__':
    raise SystemExit(main('synthetic'))
