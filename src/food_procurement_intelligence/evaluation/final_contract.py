"""Explicit final synthetic wiring and non-executable real-evaluation gate contract."""
from datetime import date,datetime,timezone

from food_procurement_intelligence.evaluation.splits import HoldoutLockedError
from food_procurement_intelligence.evaluation.sequential_runner import prepare_native_stream,EvaluationCalendar
from food_procurement_intelligence.uncertainty.horizon_sequential import HorizonSequentialOOF


FINAL_CALENDAR=EvaluationCalendar(date(2024,9,1),date(2026,6,1),date(2026,9,1))


def prepare_final_synthetic_stream(config,d4,d5,d6,plan,observations,*,publisher_factory):
    """Mandatory Day15 lifecycle; synthetic sources only, no real capability issuer.

    Day12's default factory remains a historical regression path. This entrypoint
    passes the final adapter explicitly and cannot silently use that default.
    A pinned synthetic replay publisher enables a no-fit dress rehearsal.
    """
    if (not config.get('holdout_locked') or config.get('real_execution_enabled')
        or not observations or any(r.knowledge_type!='synthetic_day12_not_world_bank' for r in observations)):
        raise HoldoutLockedError('Final entrypoint only permits explicit synthetic rehearsal')
    if (config['first_origin'],config['last_origin'],config['last_ledger'])!=('2024-09','2026-06','2026-09'):
        raise ValueError('Final22/24 calendar is frozen')
    if (d5['calibration_window'],d5['minimum_calibration_samples'],d5['nominal_coverage'])!=(60,24,.8):
        raise ValueError('Final Calibration specification is frozen')
    sc=d6['scenarios']
    if (sc['method'],sc['pool_window'],sc['minimum_joint_vectors'],sc['scenario_count'],sc['planning_seed'],sc['evaluation_seed'])!=('multiplicative_joint_oof',60,24,128,2026102901,2026102902):
        raise ValueError('Final Joint specification is frozen')
    models={k:d4[k]['model_name'] for k in ('sarimax','lightgbm')}
    selected=[]
    def factory(*args):
        pool=HorizonSequentialOOF(*args,models=models);selected.append(pool);return pool
    stream=prepare_native_stream(config,d4,d5,d6,plan,observations=observations,
        oof_factory=factory,publisher_factory=publisher_factory)
    if len(selected)!=1 or type(selected[0]) is not HorizonSequentialOOF:
        raise ValueError('Final Calibration lifecycle selection failed')
    stream['final_wiring']={'calibration_adapter':'HorizonSequentialOOF','calibration_release':'horizon',
        'joint_release':'full_vector','knowledge_type':'synthetic_day12_not_world_bank','actual_execution_capability':False}
    return stream


def publication_gate(now:datetime,threshold:datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None or threshold.tzinfo is None or threshold.utcoffset() is None:
        raise ValueError('Aware UTC-comparable timestamps required')
    return {'assessed_at_utc':now.astimezone(timezone.utc).isoformat(),'threshold_utc':threshold.astimezone(timezone.utc).isoformat(),
        'assumed_publication_mature':now>=threshold,'actual_historical_release_timestamp_verified':False}


def execution_contract(*,candidate_integrity:bool,methodology_consistent:bool,technical_ready:bool,
                       source_seed_status:str,publication_mature:bool,user_authorized:bool) -> dict:
    """Report independent gates; never grants or implements actual execution."""
    return {'A_candidate_integrity':candidate_integrity,'B_methodology_consistent':methodology_consistent,
        'C_technical_ready_synthetic':technical_ready,'D_source_seed_status':source_seed_status,
        'E_publication_mature_under_assumption':publication_mature,'F_user_authorized':user_authorized,
        'G_actual_execution_permission':False,'real_capability_implemented':False,'holdout_locked':True}


def deny_actual_evaluation() -> None:
    raise HoldoutLockedError('Day16 runbook is non-executable; no real evaluation capability or authorization')
