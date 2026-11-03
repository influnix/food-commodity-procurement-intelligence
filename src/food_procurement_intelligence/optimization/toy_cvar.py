"""Prespecified synthetic beliefs and six hand-verifiable cost distributions."""

from dataclasses import replace
from datetime import date
import hashlib
import json
from random import Random

from food_procurement_intelligence.evaluation.splits import add_months
from food_procurement_intelligence.optimization.toy_lp import hand_problems
from food_procurement_intelligence.simulation.contracts import DecisionContext, SimulationSettings, Supplier
from food_procurement_intelligence.uncertainty.joint_scenarios import PricePath, ScenarioSet, derived_seed


def synthetic_bundle(origin, prices, weights=None, model="synthetic_hand_cvar"):
    weights = weights or tuple(1/len(prices) for _ in prices)
    proof = hashlib.sha256(json.dumps([prices, weights]).encode()).hexdigest()
    paths = tuple(PricePath(f"planning|{model}|{origin:%Y-%m}|{i:04d}", date(1990, 1, 1),
                  tuple(p), w) for i, (p, w) in enumerate(zip(prices, weights)))
    return ScenarioSet(origin, model, "planning", "explicit_synthetic_not_world_bank", 0, paths, proof)


def toy_planning(origin, config: dict):
    if config["generator"] != "synthetic_joint_three_atoms_v1_not_world_or_validation":
        raise ValueError("Unsupported frozen synthetic scenario generator")
    rows = [tuple(p) for p, count in zip(config["atom_prices"], config["atom_counts"]) for _ in range(count)]
    if len(rows) != 128:
        raise ValueError("Toy uses exactly 128 prespecified paths")
    model = "synthetic_joint_three_atoms_v1"
    seed = derived_seed(config["seed"], origin, model, "planning")
    Random(seed).shuffle(rows)
    return replace(synthetic_bundle(origin, rows, model=model), seed=seed)


def cvar_hand_problems():
    base = hand_problems()
    rows = []
    for name, index, prices, weights, expected in (
        ("A_identical", 0, [(10.,10.,10.)]*128, None, (80.,80.,80.,80.)),
        ("B_tail", 0, [(10.,10.,10.),(100.,100.,100.)], (.9,.1), (190.,100.,1000.,595.)),
        ("D_lead_capacity", 1, [(10.,10.,10.)]*128, None, (220.,220.,220.,220.)),
        ("E_shortage", 4, [(10.,10.,10.),(20.,20.,20.)], (.5,.5), (6060.,6080.,6080.,6070.)),
    ):
        _, ctx, _, settings, _ = base[index]
        if name == "B_tail":
            ctx = replace(ctx, on_hand_tonnes=0.)
            settings = replace(settings, initial_inventory_tonnes=0.)
        rows.append((name,ctx,synthetic_bundle(ctx.origin,prices,weights),settings,expected))
    origin = date(2000,1,1)
    suppliers = (Supplier("A",0.,2,10.,maximum_delay_months=0), Supplier("B",.2,1,20.,maximum_delay_months=0))
    context = DecisionContext(origin,add_months(origin,2),0.,10.,suppliers,(),())
    settings = SimulationSettings(10.,0.,100.,1.,1000.,1.,0.,0.)
    bundle = synthetic_bundle(origin,[(10.,10.,10.),(10.,30.,30.)],(.9,.1))
    for name in ("C_tradeoff", "F_non_anticipativity"):
        rows.append((name,context,bundle,settings,(250.,250.,250.,250.)))
    return sorted(rows, key=lambda r:r[0])
