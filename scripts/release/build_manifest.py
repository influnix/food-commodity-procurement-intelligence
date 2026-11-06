"""Build a deterministic product tree inventory; grants no execution permission."""
import hashlib
import json
from pathlib import Path
import sys
import tomllib

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
MANIFEST = 'evidence/product_release_manifest.json'


def build(root: Path = ROOT) -> dict:
    names = tomllib.loads((root / 'configs/evaluation/release_allowlist.toml').read_text(encoding='utf-8'))['files']
    if any(Path(n).parts[0] in ('data', 'artifacts', '.git', '.venv') for n in names):
        raise ValueError('Manifest must not open source prices or local execution archives')
    files = {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names if n != MANIFEST}
    value = {'kind': 'PRODUCT_TREE_MANIFEST_NOT_EXECUTION_CANDIDATE',
             'baseline_commit': '874da83178ab15bc7f2a661fbba2b38b4875ab88',
             'files': files, 'self_hash_excluded': True, 'expected_contract_cases': 330,
             'synthetic_subset_cases': 6, 'source_access_granted': False,
             'actual_holdout_execution_allowed': False, 'historical_candidates_reused': False}
    (root / MANIFEST).write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return value


if __name__ == '__main__':
    print(json.dumps({'files_pinned': len(build()['files']), 'actual_execution_allowed': False}))
