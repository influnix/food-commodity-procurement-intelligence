"""Native integration on synthetic observations; real Holdout access remains disabled."""

from food_procurement_intelligence.configuration import historical_config_path

import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import tomllib
from uuid import uuid4

from food_procurement_intelligence.data.sequential import integration_source_guard
from food_procurement_intelligence.evaluation.preflight_runner import save
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.evaluation.model_backtesting import save_csv
from food_procurement_intelligence.evaluation.pre_holdout_audit import baseline_evidence,environment_audit
from food_procurement_intelligence.evaluation.release_gate import file_digest,preservation_check
from food_procurement_intelligence.evaluation.sequential_runner import prepare_native_stream,EvaluationCalendar,run_policy_calendar
from food_procurement_intelligence.evaluation.splits import load_split_plans,parse_month_label


def save_gzip(path: Path,value) -> None:
    path.write_bytes(gzip.compress(json.dumps(_serializable(value),sort_keys=True).encode(),mtime=0))


def run_native_integration(root: Path) -> dict:
    with integration_source_guard(root) as access:
        def read(name):return tomllib.loads((root/'configs'/name).read_text(encoding='utf-8'))
        c=read('evaluation/native_synthetic.toml')
        if not c['holdout_locked'] or c['real_execution_enabled']:raise PermissionError('No real execution mode')
        run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8]
        directory=root/'artifacts/day12'/('run_'+run_id);directory.mkdir(parents=True,exist_ok=False)
        fixture=root/'data/synthetic/day12'/('run_'+run_id);fixture.mkdir(parents=True,exist_ok=False)
        d4,d5,d6,d7,d8=(read(historical_config_path(n).removeprefix('configs/')) for n in (4,5,6,7,8));plan,_=load_split_plans(root/'configs/evaluation/splits.toml')
        code_at_start={p.relative_to(root).as_posix():file_digest(p) for p in sorted((root/'src').rglob('*.py'))}
        save(directory/'config_copy.json',c)
        try:
            stream=prepare_native_stream(c,d4,d5,d6,plan,directory)
            save(fixture/'observations.json',[asdict(p) for p in stream['observations']])
            for key in ('pool_audit','oof_released','calibrated','calibration_audit','release_log','oof_issue_log'):
                save_gzip(directory/(key+'.json.gz'),stream[key])
            calendars={'final_shape':EvaluationCalendar(parse_month_label(c['first_origin']),parse_month_label(c['last_origin']),parse_month_label(c['last_ledger'])),
                'validation_shape':EvaluationCalendar(plan.validation_origin_start,plan.validation_origin_end,plan.validation_target_end)}
            summaries={}
            for label,calendar in calendars.items():
                result=run_policy_calendar(stream,calendar,d4,d6,d7,d8);target=directory/label;target.mkdir()
                save(fixture/(label+'_operations.json'),{'settings':result['settings'],'suppliers':result['suppliers'],
                    'knowledge_type':c['fixture_knowledge_type'],'demand':100.,'realized_extra_delay':0,'initial_pipeline':[]})
                for name,r in result['results'].items():
                    for kind in ('ledger','orders','receipts'):save_csv(target/(name+'_'+kind+'.csv'),_serializable(r[kind]))
                    save(target/(name+'_decision_audit.json'),r['decision_audit']);save(target/(name+'_runoff.json'),r['runoff_no_action'])
                    save_gzip(target/(name+'_plans.json.gz'),result['plans'][name])
                for key in ('metrics','monthly','paired','input_audit','calendar'):save(target/(key+'.json'),result[key])
                save(target/'solver_timing.json',result['timing'])
                summary={'complete':result['complete'],'calendar':result['calendar'],'optimal_solves':result['optimal_solves'],
                    'policy_decisions':sum(len(r['decision_audit']) for r in result['results'].values()),
                    'ledger_rows':sum(len(r['ledger']) for r in result['results'].values()),'fallback_count':0,
                    'policy_failures':{n:r['failure'] for n,r in result['results'].items() if not r['complete']}}
                summaries[label]=summary
                if not result['complete']:raise RuntimeError('Incomplete seven-policy integration: '+label+str(summary))
            save(directory/'summary.json',{'complete':True,'calendars':summaries,'native_issued_origins_per_model':len(stream['issued'])//2,
                'native_sarimax_fits':sum(e['model']=='sarimax' for e in stream['events']),
                'native_lightgbm_fits':sum(e['model']=='lightgbm' for e in stream['events']),
                'new_real_price_fits':0,'actual_source_opens':access['actual_source_opens'],
                'source_kind':c['fixture_knowledge_type'],'synthetic_directory':fixture.relative_to(root).as_posix()})
            save(directory/'baseline_regression.json',baseline_evidence(root))
            save(directory/'environment.json',environment_audit(root))
            save(directory/'preservation.json',preservation_check(root,json.loads((root/'artifacts/day12/preservation_before.json').read_text())))
        except Exception as error:
            save(directory/'failure.json',{'error_type':type(error).__name__,'error':str(error),
                'complete':False,'full_comparison_allowed':False,'fallback':None,'holdout_locked':True})
            save(directory/'access_audit.json',access)
            return {'directory':directory.relative_to(root).as_posix(),'complete':False,'error':str(error)}
        save(directory/'access_audit.json',access)
        outputs={p.relative_to(directory).as_posix():file_digest(p) for p in sorted(directory.rglob('*')) if p.is_file() and 'timing' not in p.name}
        save(directory/'run_manifest.json',{'complete':True,'outputs':outputs,'synthetic_directory':fixture.relative_to(root).as_posix(),
            'code_at_start':code_at_start,
            'synthetic_outputs':{p.name:file_digest(p) for p in fixture.iterdir()},'config_sha256':file_digest(root/'configs/evaluation/native_synthetic.toml'),
            'raw_metadata_basis':'Day11 recorded source hashes reused; real source not opened','holdout_locked':True})
        return {'directory':directory.relative_to(root).as_posix(),'complete':True,'summary':summaries}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    result=run_native_integration(Path.cwd());print(json.dumps(_serializable(result),indent=2))
    if not result['complete']:raise SystemExit(1)
