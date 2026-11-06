"""Candidate freeze and independent readiness/clock/authorization gates. Never unlocks."""

from datetime import datetime,timezone
import json
from pathlib import Path
import tomllib

from food_procurement_intelligence.data.sequential import integration_source_guard
from food_procurement_intelligence.evaluation.preflight_runner import save
from food_procurement_intelligence.evaluation.release_gate import REQUIRED_CHECKS,file_digest,preservation_check,release_status


def execution_boundary(checks: dict,now: datetime,publication_at: datetime) -> dict:
    if now.tzinfo is None or publication_at.tzinfo is None:raise ValueError('Aware real clock required')
    gate=release_status(checks)
    return {'technical_readiness':gate['status'],'technical_gate':gate,'assessed_at_utc':now.astimezone(timezone.utc).isoformat(),
        'target_publication_assumption_utc':publication_at.isoformat(),'target_publication_maturity':now>=publication_at,
        'explicit_user_authorization':False,'real_data_capability_enabled':False,'actual_holdout_execution_allowed':False,
        'holdout_locked':True,'clock_basis':'real UTC system clock, never the synthetic session clock'}


def verify_candidate(path: Path,expected_sha256: str,root: Path) -> dict:
    def blocked(reason):return release_status({},[reason])
    if path.resolve().is_relative_to((root/'data').resolve()):return blocked('source_path_forbidden')
    if not path.is_file() or file_digest(path)!=expected_sha256:return blocked('candidate_digest_changed_or_old_approval')
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if any(not value.get(k) for k in ('contract_files','code_files','metadata_files','release_gate','preflight_baseline_sha256','readiness')):
            return blocked('incomplete_candidate')
        for group in ('contract_files','code_files','metadata_files'):
            for name,digest in value[group].items():
                p=(root/name).resolve()
                if p.is_relative_to((root/'data').resolve()) or not p.is_relative_to(root.resolve()):return blocked('forbidden_hash_path')
                if not p.is_file() or file_digest(p)!=digest:return blocked('changed_pinned_file:'+name)
        for entry in value.get('synthetic_manifests',[]):
            directory=(root/entry['directory']).resolve()
            if not directory.is_relative_to((root/'data/synthetic/day12').resolve()):return blocked('invalid_synthetic_directory')
            for name,digest in entry['files'].items():
                p=(directory/name).resolve()
                if not p.is_relative_to(directory) or not p.is_file() or file_digest(p)!=digest:return blocked('synthetic_input_changed')
        if set(value['release_gate']['checks'])!=set(REQUIRED_CHECKS):return blocked('missing_required_check')
        derived=release_status(value['release_gate']['checks'])
        if value['release_gate']!=derived:return blocked('inconsistent_gate')
        if value['readiness']['actual_holdout_execution_allowed'] or not value['readiness']['holdout_locked']:return blocked('unlock_forbidden')
        return derived
    except (KeyError,TypeError,ValueError):return blocked('malformed_candidate')


def freeze_candidate(root: Path,run: Path,repeat: Path) -> dict:
    with integration_source_guard(root) as access:
        load=lambda p:json.loads(p.read_text(encoding='utf-8'))
        c=tomllib.loads((root/'configs/evaluation/native_synthetic.toml').read_text(encoding='utf-8'))
        baseline=load(root/'artifacts/day12/preflight_baseline_integrity.json')
        if not baseline['passed'] or file_digest(root/c['preflight_baseline'])!=c['preflight_baseline_sha256']:raise ValueError('Day11 baseline changed')
        preserved=preservation_check(root,load(root/'artifacts/day12/preservation_before.json'))
        for directory in (run,repeat):
            manifest=load(directory/'run_manifest.json')
            if not manifest['complete'] or not manifest.get('code_at_start'):raise ValueError('Incomplete/unbound native experiment')
            for p,digest in manifest['code_at_start'].items():
                if file_digest(root/p)!=digest:raise ValueError('Code changed after experiment:'+p)
            environment=load(directory/'environment.json');audit=load(directory/'access_audit.json')
            if not environment['all_pins_match'] or not environment['python_matches_3_11_5'] or audit['actual_source_opens'] or audit['blocked_attempts']:
                raise ValueError('Environment or source boundary evidence failed')
            if not load(directory/'baseline_regression.json')['passed']:raise ValueError('Baseline regression failed')
        evidence={name:load(root/'artifacts/day12'/name) for name in ('test_results.json','verification_canonical.json','verification_repeat.json','repeat_comparison.json')}
        tests=evidence['test_results.json'];comparison=evidence['repeat_comparison.json']
        if not tests['passed'] or tests['previous_tests']!=359 or not comparison['passed']:raise ValueError('Required tests/repeat evidence absent')
        for name,directory in (('verification_canonical.json',run),('verification_repeat.json',repeat)):
            v=evidence[name]
            if not v['passed'] or v['run_manifest_sha256']!=file_digest(directory/'run_manifest.json'):raise ValueError('Independent evidence mismatch')
        checks={k:'PASS' for k in REQUIRED_CHECKS}
        gate=release_status(checks)
        boundary=execution_boundary(checks,datetime.now(timezone.utc),datetime.fromisoformat(c['publication_maturity_utc']))
        contract=[*sorted(p for p in (root/'configs').iterdir() if p.suffix in ('.toml','.json')),
            *sorted((root/'requirements').glob('*-lock.txt')),root/'AGENTS.md',root/'pyproject.toml',
            *[root/'docs'/n for n in ('DAY11_PRE_HOLDOUT_PROTOCOL.md','DAY11_LIMITATIONS.md','DAY12_PRODUCTION_INTEGRATION.md','DAY12_RELEASE_READINESS.md')]]
        code=[*sorted((root/'src').rglob('*.py')),*sorted((root/'tests').glob('test_*.py')),
            root/'scripts/compatibility/run_native_archive_tests.py',root/'scripts/validation/verify_native_integration.py',root/'scripts/compatibility/freeze_native_candidate.py']
        metadata=[root/'artifacts/day12'/n for n in ('preflight_baseline_integrity.json','preservation_before.json',*evidence)]
        metadata.extend([run/'run_manifest.json',repeat/'run_manifest.json',root/c['preflight_baseline'],root/'docs/DATA_AND_ASOF_CONTRACT.md'])
        # Pin every non-price run artifact; own synthetic prices remain in separate immutable manifests.
        metadata.extend(p for directory in (run,repeat) for p in sorted(directory.rglob('*')) if p.is_file() and 'timing' not in p.name)
        shared_before=load(root/'artifacts/day12/preservation_before.json')['append_only']
        changes=[{'path':n,'old_sha256':v['sha256'],'current_sha256':file_digest(root/n),'change':'append Day12 documentation only'} for n,v in shared_before.items()]
        prior=load(root/c['preflight_baseline'])
        value={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'preflight_baseline_sha256':c['preflight_baseline_sha256'],'release_gate':gate,'readiness':boundary,
            'contract_files':{p.relative_to(root).as_posix():file_digest(p) for p in contract},
            'code_files':{p.relative_to(root).as_posix():file_digest(p) for p in code},
            'metadata_files':{p.relative_to(root).as_posix():file_digest(p) for p in metadata},
            'synthetic_manifests':[{'directory':load(d/'run_manifest.json')['synthetic_directory'],
                'files':load(d/'run_manifest.json')['synthetic_outputs']} for d in (run,repeat)],
            'source_metadata':prior['source_metadata'],'preservation':preserved,'append_only_changes':changes,
            'config':c,'actual_source_access':access,'native_backend_evidence':evidence,
            'approval_binding':'Only this new external digest can identify the candidate. No approval exists; real execution stays disabled.',
            'statistical_limitations':'docs/LIMITATIONS_AND_FUTURE_WORK.md; synthetic integration does not establish forecasting accuracy or market risk coverage'}
        name='candidate_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path=root/'artifacts/day12'/(name+'.json');save(path,value);digest=file_digest(path)
        if verify_candidate(path,c['preflight_baseline_sha256'],root)['status']!='BLOCKED':raise AssertionError('Old approval unexpectedly accepted')
        if verify_candidate(path,digest,root)['status']!='READY':raise AssertionError('Candidate integrity failed')
        save(root/'artifacts/day12/candidate_pointer.json',{'path':path.relative_to(root).as_posix(),'sha256':digest,'readiness':boundary})
        return {'candidate':path.relative_to(root).as_posix(),'sha256':digest,'readiness':boundary}
