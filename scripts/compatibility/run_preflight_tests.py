"""Run the complete suite under the Day11 Python-level source access guard."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))

from datetime import datetime,timezone
import json
from pathlib import Path
from time import perf_counter

import pytest

from food_procurement_intelligence.evaluation.release_gate import source_read_guard

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())


class TestEvidence:
    def pytest_collection_finish(self,session):
        self.previous=sum('test_day11_' not in item.nodeid for item in session.items)
        self.new=len(session.items)-self.previous

    def pytest_terminal_summary(self,terminalreporter):
        self.counts={k:len(v) for k,v in terminalreporter.stats.items() if k in ('passed','failed','error','skipped','warnings')}


if __name__=='__main__':
    plugin=TestEvidence();started=perf_counter()
    with source_read_guard(ROOT) as access:
        code=pytest.main(['-q'],plugins=[plugin])
        value={'command':r'.\.venv\Scripts\python.exe scripts/compatibility/run_preflight_tests.py (pytest.main(["-q"]) under source_read_guard)',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'exit_code':int(code),'counts':plugin.counts,
            'previous_tests':plugin.previous,'new_tests':plugin.new,'elapsed_seconds':round(perf_counter()-started,2),
            'passed':code==0 and plugin.previous==324 and plugin.counts.get('passed')==plugin.previous+plugin.new and not access['blocked_attempts'] and access['actual_source_opens']==0,
            'source_access_audit':access,'intentional_negative_probes':'nested guards; no underlying source opens'}
        (ROOT/'artifacts/day11/test_results.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if value['passed'] else 1)
