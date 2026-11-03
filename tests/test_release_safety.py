"""Release boundary checks; no market data or local experiment archive."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portfolio_release_audit', ROOT / 'scripts/release/audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.mark.parametrize('name', ['data/approved_exports/final/history.csv', 'artifacts/run/summary.json',
                                  '.env', '../outside.py', '/tmp/outside.py', 'src/key.pem'])
def test_release_rejects_forbidden_paths(name):
    assert not audit.safe_name(name)


def test_release_allowlist_links_and_content():
    report = audit.audit_files(ROOT, audit.release_files())
    assert report['passed'], report['findings']


def test_secret_and_machine_path_detection():
    assert 'credential_token' in audit.content_findings(('gh' + 'p_' + 'a' * 36).encode())
    assert 'machine_path' in audit.content_findings(('C:' + chr(92) + 'Users' + chr(92) + 'example').encode())
    assert not audit.content_findings(b'explicit toy fixture, no credentials')


def test_aggregate_results_remain_validation_only():
    summary = json.loads((ROOT / 'evidence/portfolio_summary.json').read_text(encoding='utf-8'))
    policies = {r['policy']: r for r in summary['policy_comparison'] if r['period'] == 'full'}
    assert policies['fa_sarimax']['total_cost'] - policies['fixed']['total_cost'] == pytest.approx(14412.48)
    assert policies['fa_sarimax']['unmet_tonnes'] == 20
    assert summary['actual_holdout_evaluated'] is False
    assert summary['source_export_status'] == 'ACCESS_APPROVAL_REQUIRED'
    for row in summary['policy_comparison']:
        assert row['total_cost'] == pytest.approx(sum(row[k] for k in ('procurement_cost', 'transport_cost',
                    'holding_cost', 'unmet_cost', 'disposal_cost', 'terminal_cost')))
