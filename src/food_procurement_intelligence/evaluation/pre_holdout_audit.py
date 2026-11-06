"""Static production capability audit and date-only final calendar."""

from pathlib import Path
import json
import sys
from importlib.metadata import version

from food_procurement_intelligence.evaluation.splits import add_months,load_split_plans,months_between,parse_month_label
from food_procurement_intelligence.evaluation.release_gate import file_digest


def final_calendar(config: dict, root: Path) -> dict:
    plan,_=load_split_plans(root/config['split_config'])
    c=config['calendar'];first,last=parse_month_label(c['first_origin']),parse_month_label(c['last_origin'])
    origins=months_between(first,last);ledger=months_between(plan.holdout_target_start,plan.holdout_target_end)
    if (first!=plan.selection_freeze_origin or last!=add_months(plan.holdout_target_end,-3)
        or c['first_ledger']!=plan.holdout_target_start.strftime('%Y-%m') or c['last_ledger']!=plan.holdout_target_end.strftime('%Y-%m')
        or len(origins)!=22 or len(ledger)!=24 or sum(m<=last for m in ledger)!=21
        or (c['decision_count'],c['ledger_count'],c['active_count'],c['runoff_count'])!=(22,24,21,3)
        or c['runoff_new_orders'] or c['bridge_month']!='2024-09'):
        raise ValueError('Final calendar differs from frozen split')
    return {'origins':[m.strftime('%Y-%m') for m in origins],'ledger_months':[m.strftime('%Y-%m') for m in ledger],
        'active_months':[m.strftime('%Y-%m') for m in ledger if m<=last],
        'runoff_months':[m.strftime('%Y-%m') for m in ledger if m>last],
        'last_origin_targets':[add_months(last,h).strftime('%Y-%m') for h in (1,2,3)],
        'bridge_scored':False,'first_price_cutoff':add_months(first,-1).strftime('%Y-%m'),'values_read':False}


def source_finding(root: Path, path: str, tokens: tuple[str,...], explanation: str) -> dict:
    lines=(root/path).read_text(encoding='utf-8').splitlines()
    matches=[{'line':i+1,'text':line.strip()} for i,line in enumerate(lines) if any(t in line for t in tokens)]
    if not matches:raise ValueError('Audit evidence disappeared: '+path)
    return {'path':path,'sha256':file_digest(root/path),'evidence':matches,'finding':explanation}


def pipeline_audit(root: Path) -> dict:
    prefix='src/food_procurement_intelligence/'
    findings=[
      source_finding(root,prefix+'data/availability.py',('selection_freeze_origin','Bridge and holdout values'),
        'Production development store blocks all final origins and bridge; authorized sequential bridge/previous-target capability is absent.'),
      source_finding(root,prefix+'optimization/forecast_adapter.py',('validation_origin_start','Holdout/non-validation'),
        'Saved validation point adapter cannot issue new final-origin forecasts.'),
      source_finding(root,prefix+'uncertainty/calibration.py',('partition not in','phase not in','Cannot add bridge/holdout'),
        'Production OOF phase/partition support excludes bridge and Holdout even when mature; new authorized scope is required.'),
      source_finding(root,prefix+'uncertainty/joint_scenarios.py',('restricted to frozen development','validation_origin_start'),
        'Production joint generator enforces validation-only origins and targets; synthetic math is not production readiness.'),
      source_finding(root,prefix+'evaluation/day9.py',('fixed_decisions',"validation_origin_start",'validation_target_end'),
        'Day9 CLI is validation-bound and its fixed_decisions uses36. It must not be pointed at Holdout.'),
      source_finding(root,prefix+'evaluation/sensitivity.py',("['ledger'][34]",'validation_origin_end'),
        'Day10 reporting uses ledger index34 and validation boundaries; it is not a 21-active/24-month final runner.'),
      source_finding(root,prefix+'evaluation/policy_backtest.py',('months_between(first,last)','months_between(world.start,world.end)'),
        'Core execution adapter is calendar-generic; synthetic22/24 verification is possible without modifying it.'),
      source_finding(root,prefix+'forecasting/sarimax.py',('history_as_of','forecast(steps=4)','float(path[h])'),
        'SARIMAX callable accepts an as-of store and four-step output; injected-backend test can verify2/3/4 mapping.'),
      source_finding(root,prefix+'features/price.py',('TrainingBatch','assert_training_samples_available','checked_history'),
        'Features and mature labels are obtained through capability calls, not direct CSV access.'),
    ]
    return {'production_findings':findings,'production_ready':False,'native_holdout_backend_integration':'NOT_VERIFIED',
        'real_holdout_metrics':'NOT_VERIFIED','development_guard_preserved':True,
        'selection_history':[
            {'stage':'Day0','type':'initial_design','selection':'information timing and synthetic baseline'},
            {'stage':'Day2','type':'calendar_correction','selection':'publication-lag target maturity, no price-based split choice'},
            {'stage':'Day4','type':'validation_selection','selection':'SARIMAX MAE41.8757 vs LGB48.6620; same validation used'},
            {'stage':'Day5','type':'post_model_selection_uncertainty','selection':'frozen rolling OOF; coverage below80%'},
            {'stage':'Day9','type':'validation_operating_evaluation','selection':'no new model selection;7policies kept'},
            {'stage':'Day10','type':'posthoc_sensitivity','selection':'not independent preregistration; no default replaced'}]}


def environment_audit(root: Path) -> dict:
    packages={}
    for line in (root/'requirements/runtime-lock.txt').read_text(encoding='utf-8').splitlines():
        if '==' in line and not line.startswith('#'):
            name,expected=line.strip().split('==');observed=version(name)
            packages[name]={'expected':expected,'observed':observed,'matches':expected==observed}
    from ortools.linear_solver import pywraplp,_pywraplp
    solver=pywraplp.Solver.CreateSolver('GLOP')
    return {'python':sys.version,'python_matches_3_11_5':sys.version_info[:3]==(3,11,5),'packages':packages,
        'all_pins_match':all(v['matches'] for v in packages.values()),'solver':solver.SolverVersion(),
        'solver_binary_sha256':file_digest(Path(_pywraplp.__file__))}


def baseline_evidence(root: Path) -> dict:
    gate=json.loads((root/'artifacts/day10/baseline_regression.json').read_text(encoding='utf-8'))
    if not gate['passed'] or gate['exact_flow_files']!=21:raise ValueError('Recorded baseline regression did not pass')
    directory=root/gate['directory'];reference=root/'artifacts/day9/20261030T090528446877Z'
    for name in gate['checked_files']:
        if file_digest(directory/name)!=file_digest(reference/name):raise ValueError('Baseline artifact mismatch')
    from food_procurement_intelligence.evaluation.sensitivity import baseline_gate
    recomputed=baseline_gate(directory,reference)
    if recomputed['period_metric_rows']!=21:raise ValueError('Incomplete baseline period metrics')
    qa=json.loads((root/'artifacts/day10/final_qa.json').read_text(encoding='utf-8'))
    if not qa['passed'] or qa['all_tests']!=324:raise ValueError('Day10 QA evidence incomplete')
    return {'passed':True,'flow_files_rechecked_without_source_prices':21,'day10_previous_tests':324,
            'period_metric_rows_rechecked':21,
            'baseline_gate_sha256':file_digest(root/'artifacts/day10/baseline_regression.json')}
