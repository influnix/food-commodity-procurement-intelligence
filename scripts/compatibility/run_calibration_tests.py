"""Full 451-case baseline plus remediation regressions under deny-all-data guard."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
from datetime import datetime,timezone
import json
from time import perf_counter
import pytest
from scripts.compatibility.replay_support import ROOT,no_data_access,save


class Results:
    def pytest_collection_finish(self,session):
        self.previous=sum('test_day15_' not in t.nodeid for t in session.items);self.new=len(session.items)-self.previous
    def pytest_terminal_summary(self,terminalreporter):
        self.counts={k:len(v) for k,v in terminalreporter.stats.items() if k in ('passed','failed','error','skipped','warnings')}


if __name__=='__main__':
    result=Results();started=perf_counter()
    with no_data_access(ROOT) as access:
        code=pytest.main(['-q'],plugins=[result])
        value={'command':r'.\.venv\Scripts\python.exe scripts/compatibility/run_calibration_tests.py','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'exit_code':int(code),'counts':result.counts,'previous_tests':result.previous,'new_tests':result.new,
            'source_access':access,'elapsed_seconds':round(perf_counter()-started,2),
            'existing_regression_synthetic_native_fits_only':True,'new_actual_price_fits':0,
            'passed':code==0 and result.previous==451 and result.counts.get('passed')==result.previous+result.new and not access['blocked_attempts']}
        path=ROOT/'artifacts/day15/test_results.json'
        if path.exists():raise FileExistsError('Use a new evidence filename instead of overwriting')
        save(path,value)
    raise SystemExit(0 if value['passed'] else 1)
