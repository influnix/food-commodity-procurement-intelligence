"""Independent stored-evidence arithmetic and release hashes; never fit or optimize."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

from scripts.reproducibility.portfolio_evidence import no_data_access

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def equal(a,b):assert math.isclose(float(a),float(b),abs_tol=1e-6,rel_tol=1e-10),(a,b)


def verify(bundle: Path,repeat: Path|None=None) -> dict:
    with no_data_access(ROOT) as access:
        manifest=load(bundle/'evidence_release_manifest.json')
        assert manifest['kind']=='MVP_SAVED_EVIDENCE_RELEASE_NOT_HOLDOUT_FREEZE'
        assert manifest['holdout_locked'] and not manifest['actual_holdout_execution_allowed'] and not manifest['old_candidate_valid_for_added_day13_code']
        for r in manifest['references']:
            p=(ROOT/r['path']).resolve();assert p.is_relative_to(ROOT) and not p.is_relative_to(ROOT/'data')
            assert p.exists() and digest(p)==r['sha256'] and p.stat().st_size==r['size_bytes']
        for name,h in manifest['outputs'].items():assert digest(bundle/name)==h
        comparison=rows(bundle/'forecast_comparison.csv');checked=0
        for r in manifest['references']:
            p=ROOT/r['path']
            if p.name not in ('predictions.csv','validation_predictions.csv'):continue
            values=rows(p);assert len(values)==108 and len({(x['forecast_origin'],x['horizon']) for x in values})==108
            model=values[0]['model_name']
            for summary in [x for x in comparison if x['model']==model]:
                selected=[x for x in values if summary['horizon']=='overall' or x['horizon']==summary['horizon']]
                equal(summary['mae'],mean(abs(float(x['actual_price'])-float(x['predicted_price'])) for x in selected))
                equal(summary['mase'],mean(abs(float(x['actual_price'])-float(x['predicted_price']))/float(x['mase_scale']) for x in selected))
            checked+=len(values)
        assert checked==324
        policies=rows(bundle/'policy_comparison.csv');monthly=rows(bundle/'monthly_ledger_summary.csv')
        for summary in policies:
            selected=[r for r in monthly if r['policy']==summary['policy'] and (summary['period']=='full' or summary['period']==r['period'])]
            assert len(selected)==int(summary['months'])
            for key in ('procurement_cost','transport_cost','holding_cost','unmet_cost','disposal_cost','terminal_cost','total_cost'):equal(summary[key],sum(float(r[key]) for r in selected))
            equal(summary['fill_rate'],1-sum(float(r['unmet_demand']) for r in selected)/(100*len(selected)))
        for policy in ('fixed','fa_sarimax'):
            d=ROOT/'artifacts/day9/20261030T090528446877Z';ledger=rows(d/(policy+'_ledger.csv'));receipts=rows(d/(policy+'_receipts.csv'))
            assert len(ledger)==38 and len({r['order_id'] for r in receipts})==len(receipts)
            inventory=200
            for r in ledger:
                received=sum(float(x['quantity_tonnes']) for x in receipts if x['receipt_month']==r['month'])
                equal(r['beginning_inventory'],inventory)
                available=inventory+received;served=min(available,100);inventory=max(available-100,0)
                equal(r['ending_inventory'],inventory);equal(r['unmet_demand'],100-served)
                procurement=sum(float(x['procurement_cost']) for x in receipts if x['receipt_month']==r['month'])
                equal(r['procurement_cost'],procurement)
                terminal=abs(inventory-200)*9 if r['month']=='2024-08' else 0
                equal(r['terminal_cost'],terminal)
                equal(r['total_cost'],procurement+inventory*3+(100-served)*1500+terminal)
                if r['period']=='runoff':equal(r['new_order_quantity'],0)
        diagnostic=load(bundle/'cost_service_diagnosis.json');delta=diagnostic['components_fa_minus_fixed']
        equal(delta['total_cost'],14412.48);equal(delta['total_cost'],sum(delta[k] for k in ('procurement_cost','transport_cost','holding_cost','unmet_cost','disposal_cost','terminal_cost')))
        equal(diagnostic['maximum_supply_from_last_state'],280);equal(diagnostic['unavoidable_shortage_from_this_state'],20)
        matrix=load(bundle/'acceptance_matrix.json');assert len(matrix)==5 and all(r['status']=='PASS' for r in matrix)
        tests=load(bundle/'test_evidence.json');assert tests['passed'] and tests['previous_tests']==403
        byte_equal=0
        if repeat:
            other=load(repeat/'evidence_release_manifest.json');assert manifest==other
            for name in [*manifest['outputs'],'evidence_release_manifest.json']:
                assert (bundle/name).read_bytes()==(repeat/name).read_bytes();byte_equal+=1
        return {'passed':True,'forecast_rows_checked':324,'representative_policy_months_checked':76,'acceptance_passed':5,
            'reference_files_checked':len(manifest['references']),'deterministic_files_equal':byte_equal,'source_access':access,
            'evidence_release_sha256':digest(bundle/'evidence_release_manifest.json'),'holdout_locked':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--repeat',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=verify(a.bundle.resolve(),a.repeat.resolve() if a.repeat else None)
    a.output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');print(json.dumps(value))
