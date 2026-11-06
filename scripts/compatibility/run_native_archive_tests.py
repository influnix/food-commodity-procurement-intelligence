"""Run every regression and integration test under the source access guard."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
from datetime import datetime,timezone
import json
from pathlib import Path
from time import perf_counter
import pytest
from food_procurement_intelligence.data.sequential import integration_source_guard

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
class Evidence:
    def pytest_collection_finish(self,session):
        self.previous=sum('test_day12_' not in t.nodeid for t in session.items);self.new=len(session.items)-self.previous
    def pytest_terminal_summary(self,terminalreporter):
        self.counts={k:len(v) for k,v in terminalreporter.stats.items() if k in ('passed','failed','error','skipped','warnings')}
if __name__=='__main__':
    p=Evidence();start=perf_counter()
    with integration_source_guard(ROOT) as audit:
        code=pytest.main(['-q'],plugins=[p]);value={'command':r'.\.venv\Scripts\python.exe scripts/compatibility/run_native_archive_tests.py',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'exit_code':int(code),'counts':p.counts,'previous_tests':p.previous,'new_tests':p.new,
            'elapsed_seconds':round(perf_counter()-start,2),'source_access_audit':audit,
            'passed':code==0 and p.previous==359 and p.counts.get('passed')==p.previous+p.new and not audit['blocked_attempts']}
        (ROOT/'artifacts/day12/test_results.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if value['passed'] else 1)
