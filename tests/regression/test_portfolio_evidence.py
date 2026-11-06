"""Saved evidence and clearly synthetic unit values; no source data or new fit."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
spec=importlib.util.spec_from_file_location('day13_evidence',ROOT/'scripts/reproducibility/portfolio_evidence.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def toy_forecasts():
    result=[]
    for i in range(module.index('2021-06'),module.index('2024-05')+1):
        o=module.month(i)
        for h in (1,2,3):result.append({'forecast_origin':o,'information_cutoff':module.month(i-1),'target_month':module.month(i+h),
            'horizon':str(h),'forecast_asof_at':module.stamp(o),'steps_from_latest_observation':str(h+1),'unit':'USD_per_metric_tonne',
            'predicted_price':'100','actual_price':'110','mase_scale':'10','absolute_error':'10','scaled_error':'1','model_name':'EXPLICIT_TOY'})
    return result


def test_synthetic_forecast_metric_arithmetic():
    values=module.forecast_summary(toy_forecasts())
    assert values[0]['n']==108 and values[0]['mae']==10 and values[0]['mase']==1


@pytest.mark.parametrize('change',['missing','duplicate','future','cutoff','horizon','scale'])
def test_forecast_evidence_detects_bad_keys_and_values(change):
    values=toy_forecasts()
    if change=='missing':values.pop()
    elif change=='duplicate':values[-1]=values[0]
    elif change=='future':values[0]['forecast_origin']='2024-09'
    elif change=='cutoff':values[0]['information_cutoff']='2021-06'
    elif change=='horizon':values[0]['horizon']='4'
    else:values[0]['mase_scale']='0'
    with pytest.raises(ValueError):module.forecast_summary(values)


def saved_policy():
    directory=ROOT/module.D9
    # Explicitly permitted saved Validation artifacts; never a World Bank data file.
    prices={r['observation_month']:float(r['price']) for r in module.rows(directory/'evaluation_prices.csv')}
    return [module.rows(directory/('fa_sarimax_'+kind+'.csv')) for kind in ('ledger','orders','receipts')],prices


def test_saved_ledger_recomputes_exact_representative_result():
    (ledger,orders,receipts),prices=saved_policy();summaries,allocation=module.audit_policy(ledger,orders,receipts,prices)
    assert summaries[0]['total_cost']==pytest.approx(1365914.16)
    assert summaries[0]['unmet_tonnes']==20 and allocation=={'A':2880.,'B':700.}
    assert summaries[1]['months']==35 and summaries[2]['months']==3


@pytest.mark.parametrize('change',['double_terminal','duplicate_order','missing_receipt','runoff_order','wrong_price'])
def test_saved_ledger_audit_detects_accounting_changes(change):
    (ledger,orders,receipts),prices=saved_policy()
    if change=='double_terminal':ledger[-2]['terminal_cost']='1800'
    elif change=='duplicate_order':orders.append(deepcopy(orders[0]))
    elif change=='missing_receipt':receipts.pop()
    elif change=='runoff_order':ledger[-1]['new_order_quantity']='20'
    else:receipts[0]['market_price']='1'
    with pytest.raises(ValueError):module.audit_policy(ledger,orders,receipts,prices)


def test_all_data_access_denied_and_outside_output_rejected(tmp_path):
    with module.no_data_access(ROOT) as audit:
        with pytest.raises(PermissionError):(ROOT/'data/raw/DO_NOT_OPEN').read_bytes()
    assert len(audit['blocked_attempts'])==1 and audit['actual_source_opens']==0
    with pytest.raises(ValueError):module.build(ROOT,tmp_path/'not_day13',plot=False)


def test_missing_reference_and_wrong_hash_fail_closed(tmp_path):
    ref=module.References(tmp_path);p=tmp_path/'saved.txt';p.write_text('toy',encoding='utf-8')
    with pytest.raises(ValueError):ref.add('saved.txt','toy','wrong')
    with pytest.raises(FileNotFoundError):ref.add('missing.json','missing')
    with pytest.raises(PermissionError):ref.add('data/raw/blocked','source')
