"""Fail-closed audit helpers. This module has no real-data unlock capability."""

from contextlib import contextmanager
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

from food_procurement_intelligence.evaluation.splits import HoldoutLockedError


REQUIRED_CHECKS=('tests_all_pass','baseline_regression','split_calendar_frozen','seven_policies_frozen',
    'model_feature_specs_frozen','oof_calibration_contract_frozen','scenario_seeds_frozen',
    'operations_terminal_frozen','primary_secondary_metrics_frozen','synthetic_preflight_passed',
    'no_source_data_access','artifact_preservation','solver_environment_reproduced','limitations_documented',
    'production_sequential_store_bridge','production_new_origin_forecast_adapter',
    'production_oof_scenario_phase_support','production_final_runner_metrics_22_24',
    'production_new_origin_backend_integration')


@contextmanager
def source_read_guard(root: Path):
    """Deny workspace data access except newly authored Day11 synthetic fixtures."""
    data=(root/'data').resolve()
    fixture=(root/'data/synthetic/day11').resolve()
    audit={'blocked_attempts':[], 'actual_source_opens':0}
    def check(file):
        if isinstance(file,int):return
        try:path=Path(os.fsdecode(file)).resolve()
        except (TypeError,ValueError):return
        if path.is_relative_to(data) and not path.is_relative_to(fixture):
            audit['blocked_attempts'].append(path.relative_to(root).as_posix())
            raise HoldoutLockedError('Day11 prohibits source-data access; synthetic fixtures only')
    def wrap(original):
        def guarded(file,*args,**kwargs):
            check(file)
            return original(file,*args,**kwargs)
        return guarded
    with patch('builtins.open',wrap(builtins.open)),patch('io.open',wrap(io.open)),patch('os.open',wrap(os.open)):
        yield audit


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def release_status(checks: dict[str,str], integrity_violations: list[str] | None = None) -> dict:
    checks={name:checks.get(name,'NOT_VERIFIED') for name in REQUIRED_CHECKS}
    integrity_violations=list(integrity_violations or [])
    if any(value not in ('PASS','FAIL','NOT_VERIFIED') for value in checks.values()):
        integrity_violations.append('malformed_check_status')
    if integrity_violations:
        status='BLOCKED'
    elif any(value!='PASS' for value in checks.values()):
        status='NOT_READY'
    else:
        status='READY'
    return {'status':status,'checks':checks,'unresolved':[k for k,v in checks.items() if v!='PASS'],
            'integrity_violations':integrity_violations or [],'holdout_locked':True,
            'actual_holdout_execution_allowed':False,'explicit_user_approval_required':True,
            'readiness_is_not_authorization':True}


def deny_real_execution() -> None:
    raise HoldoutLockedError('Day11 has no real Holdout capability, even if technical gate is READY')


def verify_frozen_manifest(path: Path, expected_digest: str, root: Path) -> dict:
    violations=[]
    if path.resolve().is_relative_to((root/'data').resolve()):
        return release_status({},['manifest_path_must_not_be_source_data'])
    if not path.is_file() or file_digest(path)!=expected_digest:
        return release_status({},['freeze_manifest_digest_changed'])
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        required=('contract_files','code_files','metadata_files','contract','calendar','source_metadata',
                  'environment','test_status','failure_policy','release_gate','approval_binding')
        if any(not value.get(k) for k in required) or value.get('schema_version')!=1:
            return release_status({},['incomplete_freeze_manifest'])
        if set(value['release_gate']['checks'])!=set(REQUIRED_CHECKS):
            return release_status({},['incomplete_gate_checks'])
    except (ValueError,TypeError,KeyError):
        return release_status({},['malformed_freeze_manifest'])
    for group in ('contract_files','code_files','metadata_files'):
        for name,expected in value[group].items():
            file=(root/name).resolve()
            if file.is_relative_to((root/'data').resolve()):
                violations.append('source_data_hash_entry_not_allowed')
            elif not file.is_relative_to(root.resolve()) or not file.is_file() or file_digest(file)!=expected:
                violations.append(group+':'+name)
    for name,expected in value.get('outputs',{}).items():
        file=(path.parent/name).resolve()
        if (not file.is_relative_to(path.parent.resolve()) or file.is_relative_to((root/'data').resolve())
            or not file.is_file() or file_digest(file)!=expected):violations.append('output:'+name)
    if 'synthetic_outputs' in value:
        fixture=(root/value['synthetic_directory']).resolve()
        allowed=(root/'data/synthetic/day11').resolve()
        for name,expected in value['synthetic_outputs'].items():
            file=(fixture/name).resolve()
            if (not fixture.is_relative_to(allowed) or not file.is_relative_to(fixture)
                or not file.is_file() or file_digest(file)!=expected):violations.append('synthetic_output:'+name)
    checks=value['release_gate']['checks']
    derived=release_status(checks)
    if value['release_gate']!=derived:violations.append('release_result_does_not_match_checks')
    return release_status(checks,violations)


def preservation_check(root: Path, snapshot: dict) -> dict:
    for name,expected in snapshot['sha256'].items():
        if file_digest(root/name)!=expected:raise ValueError('Existing artifact changed: '+name)
    for name,info in snapshot['metadata_only'].items():
        stat=(root/name).stat()
        if stat.st_size!=info['size_bytes'] or stat.st_mtime_ns!=info['mtime_ns']:
            raise ValueError('Protected source metadata changed: '+name)
    for name,info in snapshot['append_only'].items():
        if hashlib.sha256((root/name).read_bytes()[:info['bytes']]).hexdigest()!=info['sha256']:
            raise ValueError('Existing documentation prefix changed: '+name)
    return {'hash_verified_files':len(snapshot['sha256']),'metadata_only_files':len(snapshot['metadata_only']),
            'append_only_documents':len(snapshot['append_only']),'raw_price_bytes_rehashed':False}
