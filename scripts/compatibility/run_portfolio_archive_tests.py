"""Complete regression under an all-data-directory deny guard; no new experiment."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
from datetime import datetime,timezone
import json
from pathlib import Path
from time import perf_counter
import pytest
from scripts.reproducibility.portfolio_evidence import no_data_access

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
class Evidence:
    def pytest_collection_finish(self,session):
        self.previous=sum('test_day13_' not in t.nodeid for t in session.items);self.new=len(session.items)-self.previous
    def pytest_terminal_summary(self,terminalreporter):
        self.counts={k:len(v) for k,v in terminalreporter.stats.items() if k in ('passed','failed','error','skipped','warnings')}
if __name__=='__main__':
    plugin=Evidence();started=perf_counter()
    with no_data_access(ROOT) as access:
        code=pytest.main(['-q'],plugins=[plugin])
        value={'command':r'.\.venv\Scripts\python.exe scripts/compatibility/run_portfolio_archive_tests.py','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'exit_code':int(code),'counts':plugin.counts,'previous_tests':plugin.previous,'new_tests':plugin.new,'source_access':access,
            'elapsed_seconds':round(perf_counter()-started,2),'new_model_or_policy_experiment':False,
            'existing_regression_toy_fits_reexecuted':True,
            'passed':code==0 and plugin.previous==403 and plugin.counts.get('passed')==plugin.previous+plugin.new and not access['blocked_attempts']}
        (ROOT/'artifacts/day13/test_results.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if value['passed'] else 1)
