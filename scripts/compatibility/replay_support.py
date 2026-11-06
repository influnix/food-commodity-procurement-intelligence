"""Day15 saved-synthetic utilities and explicit authorized-change accounting."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))

from food_procurement_intelligence.configuration import historical_config_path
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tomllib

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'scripts/compatibility'))
from scripts.reproducibility.portfolio_evidence import no_data_access
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable

D12=ROOT/'artifacts/day12/run_20261030T152324128300Z_6ef590c2'
def cfg(n):return tomllib.loads((ROOT/historical_config_path(n)).read_text(encoding='utf-8'))
def read(p):
    b=Path(p).read_bytes();return json.loads(gzip.decompress(b) if str(p).endswith('.gz') else b)
def save(p,value):Path(p).write_text(json.dumps(_serializable(value),sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def zipped(p,value):Path(p).write_bytes(gzip.compress(json.dumps(_serializable(value),sort_keys=True,allow_nan=False).encode(),mtime=0))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def baseline():return read(ROOT/'artifacts/day15/preservation_before.json')


def preservation() -> dict:
    old=baseline();allowed=cfg(15)['intentional_changes'];changed=[];unauthorized=[]
    for name,h in old['files'].items():
        p=ROOT/name;new=sha(p) if p.is_file() else None
        if h!=new:
            row={'path':name,'before_sha256':h,'after_sha256':new,'reason':allowed.get(name)}
            (changed if name in allowed and new else unauthorized).append(row)
    for name,s in old['data_stat_only'].items():
        p=ROOT/name
        if not p.is_file() or p.stat().st_size!=s['size'] or p.stat().st_mtime_ns!=s['mtime_ns']:
            unauthorized.append({'path':name,'reason':'protected data metadata changed'})
    return {'passed':not unauthorized,'intentional_changes':changed,'unauthorized_changes':unauthorized,
        'prior_files':len(old['files']),'unchanged_file_hashes':len(old['files'])-len(changed)-len(unauthorized),
        'data_metadata_only':len(old['data_stat_only']),'data_bytes_rehashed':False}


def scoped_legacy_snapshot(snapshot: dict) -> tuple[dict,list[str]]:
    """Never exempt artifacts: match pre-Day15 SHA before permitting a named code edit."""
    value=deepcopy(snapshot);old=baseline();allowed=cfg(15)['intentional_changes'];changed=[]
    for name,h in list(value['sha256'].items()):
        if sha(ROOT/name)==h:continue
        if name not in allowed or not name.startswith(('src/','tests/')) or old['files'].get(name)!=h:
            raise ValueError('Unapproved historical change: '+name)
        changed.append(name);del value['sha256'][name]
    return value,changed


def load_saved_batches():
    from food_procurement_intelligence.forecasting.publisher import load_issued_forecast
    m=read(D12/'run_manifest.json');result={}
    for p in sorted((D12/'issuances').glob('*.json')):
        if sha(p)!=m['outputs'][p.relative_to(D12).as_posix()]:raise ValueError('Original issuance file modified')
        value=read(p);batch=load_issued_forecast(p,value['issued_sha256'])
        result[batch.label,batch.origin]=batch
    if len(result)!=236:raise ValueError('Incomplete immutable synthetic archive')
    return result
