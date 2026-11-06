"""Complete515 baseline plus Day16 regressions; all workspace data opens forbidden."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
from datetime import datetime,timezone
from time import perf_counter
import pytest
from scripts.compatibility.handoff_support import ROOT,save,no_data_access


class Evidence:
    def pytest_collection_finish(self,session):
        self.previous=sum('test_day16_' not in t.nodeid for t in session.items);self.new=len(session.items)-self.previous
    def pytest_terminal_summary(self,terminalreporter):
        self.counts={k:len(v) for k,v in terminalreporter.stats.items() if k in ('passed','failed','error','skipped','warnings')}


if __name__=='__main__':
    e=Evidence();started=perf_counter()
    with no_data_access(ROOT) as access:
        code=pytest.main(['-q'],plugins=[e])
        v={'command':r'.\.venv\Scripts\python.exe scripts/compatibility/run_handoff_tests.py','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'exit_code':int(code),'previous_tests':e.previous,'new_tests':e.new,'counts':e.counts,'source_access':access,
            'elapsed_seconds':round(perf_counter()-started,2),'existing_regression_synthetic_native_fits_only':True,
            'actual_holdout_access_or_fit':False,'passed':code==0 and e.previous==515 and e.counts.get('passed')==e.previous+e.new and not access['blocked_attempts']}
        path=ROOT/'artifacts/day16/test_results.json'
        if path.exists():raise FileExistsError('Preserve prior test evidence')
        save(path,v)
    raise SystemExit(0 if v['passed'] else 1)
