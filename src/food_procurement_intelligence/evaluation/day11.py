"""Day11 audit/freeze CLI. There is deliberately no real-data execution mode."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import tomllib

from food_procurement_intelligence.evaluation.day6 import _serializable
from food_procurement_intelligence.evaluation.day9 import POLICIES
from food_procurement_intelligence.evaluation.model_backtesting import save_csv
from food_procurement_intelligence.evaluation.pre_holdout_audit import (
    baseline_evidence, environment_audit, final_calendar, pipeline_audit,
)
from food_procurement_intelligence.evaluation.release_gate import (
    REQUIRED_CHECKS, file_digest, preservation_check, release_status, source_read_guard,
)
from food_procurement_intelligence.evaluation.synthetic_preflight import run_synthetic_preflight


def save(path: Path, value) -> None:
    path.write_text(json.dumps(_serializable(value), ensure_ascii=False, indent=2, sort_keys=True)+'\n',encoding='utf-8')


def validate_contract(c: dict) -> None:
    if (not c['holdout_locked'] or c['real_execution_enabled'] or tuple(c['policies'])!=POLICIES
        or c['rolling']['alpha']!=.9 or c['rolling']['rn_lambda']!=0 or c['rolling']['ra_lambda']!=.5
        or c['rolling']['scenario_count']!=128 or c['rolling']['hyperparameter_search']
        or c['operations']['initial_inventory_tonnes']!=200 or c['operations']['initial_pipeline']!='empty'
        or c['metrics']['primary']!=['full_total_simulated_cost_usd','quantity_fill_rate']
        or c['metrics']['choose_single_winner']):
        raise ValueError('Final contract contradicts existing frozen baseline')


def run_day11(config_path: Path, root: Path | None = None) -> dict:
    root=(root or Path.cwd()).resolve()
    with source_read_guard(root) as access:
        def read(name):return tomllib.loads((root/'configs'/name).read_text(encoding='utf-8'))
        config=tomllib.loads((root/config_path).read_text(encoding='utf-8'));validate_contract(config)
        run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        directory=root/config['report_root']/('run_'+run_id)
        fixture=root/config['synthetic_root']/('run_'+run_id)
        # Paths are fixed to Day11: a caller cannot redirect output into old results.
        if directory.parent!=root/'artifacts/day11' or fixture.parent!=root/'data/synthetic/day11':
            raise ValueError('Day11-only output directories required')
        directory.mkdir(parents=True,exist_ok=False);fixture.mkdir(parents=True,exist_ok=False)
        calendar=final_calendar(config,root);audit=pipeline_audit(root);environment=environment_audit(root)
        baseline=baseline_evidence(root)
        preserved=preservation_check(root,json.loads((root/'artifacts/day11/preservation_before.json').read_text(encoding='utf-8')))
        tests_path=root/'artifacts/day11/test_results.json'
        tests=json.loads(tests_path.read_text(encoding='utf-8')) if tests_path.exists() else {'passed':False}
        result=run_synthetic_preflight(config,read('day4.toml'),read('day6.toml'),read('day7.toml'),read('day8.toml'))
        save(fixture/'observations.json',[asdict(p) for p in result['observations']])
        save(fixture/'operations.json',{'knowledge_type':config['synthetic']['knowledge_type'],
            'settings':asdict(result['settings']),'suppliers':[asdict(s) for s in result['suppliers']],
            'initial_pipeline':[],'demand':100.,'extra_delay':0,'price_rule':config['synthetic']['price_rule']})
        for name in ('fit_audit','pool_audit','purpose_checks','summary'):
            save(directory/(name+'.json'),result[name])
        save(directory/'solver_timing.json',result['timing'])
        for name,value in result['results'].items():
            for kind in ('orders','receipts','ledger'):
                save_csv(directory/(name+'_'+kind+'.csv'),_serializable(value[kind]))
            save(directory/(name+'_decision_audit.json'),value['decision_audit'])
            save(directory/(name+'_runoff.json'),value['runoff_no_action'])
            payload=json.dumps(_serializable(result['plans'][name]),sort_keys=True).encode()
            (directory/(name+'_plans.json.gz')).write_bytes(gzip.compress(payload,mtime=0))
        for name,value in (('calendar',calendar),('pipeline_audit',audit),('environment',environment),
                           ('baseline_regression',baseline),('preservation',preserved),('access_audit',access)):
            save(directory/(name+'.json'),value)
        checks={name:'PASS' for name in REQUIRED_CHECKS}
        checks['tests_all_pass']='PASS' if tests.get('passed') and tests.get('previous_tests')==324 else 'NOT_VERIFIED'
        checks['solver_environment_reproduced']='PASS' if environment['all_pins_match'] and environment['python_matches_3_11_5'] else 'FAIL'
        for name in checks:
            if name.startswith('production_'):checks[name]='NOT_VERIFIED'
        gate=release_status(checks,['unexpected_source_access'] if access['blocked_attempts'] else [])
        save(directory/'release_gate.json',gate)
        package=root/'src/food_procurement_intelligence'
        contract=[*sorted(p for p in (root/'configs').iterdir() if p.suffix in ('.toml','.json')),
            *sorted((root/'requirements').glob('*-lock.txt')),root/'pyproject.toml',
            root/'AGENTS.md',*[root/'docs'/n for n in ('DAY11_PRE_HOLDOUT_PROTOCOL.md','DAY11_RELEASE_GATE.md','DAY11_LIMITATIONS.md',
            'DECISION_TIMELINE.md','SPLIT_DESIGN.md','DAY5_UNCERTAINTY_DESIGN.md','DAY7_LP_SPEC.md','DAY8_CVAR_SPEC.md','DAY9_EVALUATION_PROTOCOL.md')]]
        code=[*sorted(package.rglob('*.py')),*sorted((root/'tests').glob('test_*.py')),
              root/'scripts/verify_day11_results.py',root/'scripts/run_day11_tests.py']
        metadata=[root/'artifacts/day11/preservation_before.json',root/'artifacts/day10/final_qa.json',
            root/'artifacts/day10/baseline_regression.json',root/'docs/WORLD_BANK_SOURCE.md',
            root/'artifacts/day10/run_20261030T114444326360Z/manifest.json']
        if tests_path.exists():metadata.append(tests_path)
        upstream=json.loads((root/'artifacts/day10/run_20261030T114444326360Z/manifest.json').read_text(encoding='utf-8'))
        deterministic=[p for p in directory.iterdir() if p.is_file() and p.name!='solver_timing.json']
        # Synthetic data hashes are separate from source metadata and never confer real-data access.
        manifest={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'contract':config,'calendar':calendar,'release_gate':gate,'environment':environment,
            'contract_files':{p.relative_to(root).as_posix():file_digest(p) for p in contract},
            'code_files':{p.relative_to(root).as_posix():file_digest(p) for p in code},
            'metadata_files':{p.relative_to(root).as_posix():file_digest(p) for p in metadata},
            'source_metadata':{'raw_sha256':upstream['raw_sha256'],'source_data':upstream['source_data'],
                'basis':'reused_previously_verified_Day10_manifest_not_source_bytes_read_today',
                'source_record_manifest':'artifacts/day10/run_20261030T114444326360Z/manifest.json',
                'source_record_manifest_sha256':file_digest(root/'artifacts/day10/run_20261030T114444326360Z/manifest.json'),
                'raw_url':'https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx',
                'retrieval_utc':'2026-10-24T01:29:17.500704Z','size_bytes':586099,
                'unit':'nominal USD/metric tonne','current_source_bytes_reverified':False},
            'test_status':tests,'failure_policy':config['operations']['failure_policy'],
            'outputs':{p.relative_to(directory).as_posix():file_digest(p) for p in sorted(deterministic)},
            'synthetic_outputs':{p.name:file_digest(p) for p in sorted(fixture.iterdir())},
            'synthetic_directory':fixture.relative_to(root).as_posix(),
            'actual_holdout_metrics':'NOT_VERIFIED','new_experiment_model_training':False,
            'legacy_regression_suite_may_fit_existing_toy_fixtures':True,
            'approval_binding':'Expected manifest SHA256 must be supplied externally; changes invalidate the old freeze. READY never authorizes unlock.'}
        save(directory/'final_freeze_manifest.json',manifest)
        digest=file_digest(directory/'final_freeze_manifest.json')
        save(directory/'freeze_digest.json',{'sha256':digest,'manifest':'final_freeze_manifest.json','holdout_locked':True})
        return {'directory':directory.relative_to(root).as_posix(),'freeze_sha256':digest,'gate':gate['status'],
                'synthetic_summary':result['summary'],'actual_source_opens':access['actual_source_opens']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/day11.toml'))
    args=parser.parse_args()
    print(json.dumps(run_day11(args.config),indent=2))
