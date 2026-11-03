"""All previous418 + Day14 audit tests, deny all workspace data-directory opens."""
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
import pytest
from audit import no_data_access, ROOT


class Results:
    def pytest_collection_finish(self,session):
        self.previous=sum('test_day14_' not in item.nodeid for item in session.items)
        self.new=len(session.items)-self.previous

    def pytest_terminal_summary(self,terminalreporter):
        self.counts={k:len(v) for k,v in terminalreporter.stats.items() if k in ('passed','failed','error','skipped','warnings')}


if __name__=='__main__':
    r=Results();started=perf_counter()
    with no_data_access(ROOT) as access:
        code=pytest.main(['-q'],plugins=[r])
        value={'command':r'.\.venv\Scripts\python.exe scripts/day14/run_tests.py','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'exit_code':int(code),'previous_tests':r.previous,'new_tests':r.new,'counts':r.counts,
            'elapsed_seconds':round(perf_counter()-started,2),'source_access':access,
            'existing_synthetic_regression_toy_fits_only':True,'new_forecast_fits':0,'new_procurement_experiments':False,
            'passed':code==0 and r.previous==418 and r.counts.get('passed')==r.previous+r.new and not access['blocked_attempts']}
        path=ROOT/'artifacts/day14/test_results.json'
        with path.open('x',encoding='utf-8') as f:json.dump(value,f,sort_keys=True,indent=2);f.write('\n')
    raise SystemExit(0 if value['passed'] else 1)
