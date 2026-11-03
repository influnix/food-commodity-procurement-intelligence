"""Planning-only, hash-linked Day 6 adapter; no target-answer reader."""

import csv
import hashlib
import json
from pathlib import Path

from food_procurement_intelligence.evaluation.model_backtesting import digest
from food_procurement_intelligence.evaluation.splits import (
    HoldoutLockedError, LeakageError, add_months, decision_at, parse_month_label,
)
from food_procurement_intelligence.uncertainty.joint_scenarios import (
    PricePath, ScenarioSet, derived_seed,
)


def pool_proof_view(path: Path, origin, model: str) -> list[dict]:
    """Keep every unrequested numeric price as text; select before decoding values."""
    records = json.loads(path.read_text(encoding="utf-8"), parse_float=str)
    return [r for r in records if r["source_model"] == model
            and r["construction_origin"] == origin.strftime("%Y-%m")]


def bundle_from_records(rows: list[dict], origin, model: str) -> ScenarioSet:
    """Convert three rows per path to one probability mass; reject mixed metadata."""
    if not rows:
        raise ValueError("Missing planning scenario rows")
    groups = {}
    common = ("seed", "method", "pool_sha256")
    for row in rows:
        if (row["forecast_origin"] != origin.strftime("%Y-%m") or row["source_model"] != model
                or row["purpose"] != "planning"):
            raise LeakageError("Scenario rows mix origin, model or purpose")
        if (row["forecast_asof_at"] != decision_at(origin).isoformat()
                or row["information_cutoff"] != add_months(origin, -1).strftime("%Y-%m")
                or row["unit"] != "USD_per_metric_tonne"
                or row["knowledge_type"] != "empirical_simulation_not_observed"):
            raise LeakageError("Scenario clock, cutoff, unit or knowledge type mismatch")
        if any(row[key] != rows[0][key] for key in common):
            raise ValueError("Scenario rows mix seed, method or pool")
        h = int(row["horizon"])
        if h not in (1, 2, 3) or parse_month_label(row["target_month"]) != add_months(origin, h):
            raise ValueError("Scenario target/horizon mismatch")
        key = row["scenario_id"]
        group = groups.setdefault(key, {})
        if h in group:
            raise ValueError("Duplicate scenario horizon")
        group[h] = row
    paths = []
    for key, group in sorted(groups.items()):
        if set(group) != {1, 2, 3}:
            raise ValueError("Incomplete joint price path")
        first = group[1]
        if any(r["source_oof_origin"] != first["source_oof_origin"] or float(r["probability"]) != float(first["probability"]) for r in group.values()):
            raise ValueError("Joint path changed OOF origin or repeated probability")
        paths.append(PricePath(key, parse_month_label(first["source_oof_origin"]),
            tuple(float(group[h]["price"]) for h in (1, 2, 3)), float(first["probability"])))
    first = rows[0]
    return ScenarioSet(origin, model, "planning", first["method"], int(first["seed"]), tuple(paths), first["pool_sha256"])


class SavedPlanningScenarios:
    def __init__(self, directory: Path, root: Path, plan, expected_manifest_sha256: str):
        self.directory, self.plan = directory, plan
        self.source_id = digest(directory / "manifest.json")
        if self.source_id != expected_manifest_sha256:
            raise ValueError("Frozen Day 6 manifest changed")
        self._manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if self._manifest["holdout_locked"] is not True:
            raise HoldoutLockedError("Day 6 source was not locked")
        self._root = root
        for name in ("joint_price_scenarios.csv", "joint_oof_vectors.json"):
            file = directory / name
            expected = self._manifest["output_sha256"][file.relative_to(root).as_posix()]
            if digest(file) != expected:
                raise ValueError("Day 6 scenario/proof file changed")

    def __call__(self, origin, model: str):
        if not self.plan.validation_origin_start <= origin <= self.plan.validation_origin_end:
            raise HoldoutLockedError("Saved scenarios are restricted to frozen Validation origins")
        if model not in self._manifest["config"]["models"]:
            raise ValueError("Unknown scenario forecast model")
        # Decode only the requested planning set, never evaluation prices or answers.
        with (self.directory / "joint_price_scenarios.csv").open(encoding="utf-8", newline="") as file:
            selected = [r for r in csv.DictReader(file) if r["purpose"] == "planning"
                and r["source_model"] == model and r["forecast_origin"] == origin.strftime("%Y-%m")]
        bundle = bundle_from_records(selected, origin, model)
        spec = self._manifest["config"]["scenarios"]
        if (len(bundle.paths) != spec["scenario_count"] or len(bundle.paths) != 128
                or bundle.method != spec["method"]
                or bundle.seed != derived_seed(spec["planning_seed"], origin, model, "planning")
                or any(p.weight != 1/128 for p in bundle.paths)
                or any(p.scenario_id != f"planning|{model}|{origin:%Y-%m}|{i:04d}" for i, p in enumerate(bundle.paths))):
            raise ValueError("Day 6 set cardinality/weights/seed/IDs/method changed")
        pool = pool_proof_view(self.directory / "joint_oof_vectors.json", origin, model)
        if not spec["minimum_joint_vectors"] <= len(pool) <= spec["pool_window"]:
            raise ValueError("OOF pool window mismatch")
        eligible = set()
        from datetime import datetime
        for proof in pool:
            past = parse_month_label(proof["source_oof_origin"])
            if (past >= origin or add_months(past, 3) > add_months(origin, -1)
                    or proof["horizons"] != [1, 2, 3]
                    or proof["target_months"] != [add_months(past, h).strftime("%Y-%m") for h in (1, 2, 3)]):
                raise LeakageError("Incomplete or immature OOF vector")
            for h in range(3):
                target = parse_month_label(proof["target_months"][h])
                available = datetime.fromisoformat(proof["actual_available_at"][h])
                fit_stamp = datetime.fromisoformat(proof["fit_max_label_available_at"][h])
                if (self.plan.target_partition(target) not in ("train", "validation")
                        or available.tzinfo is None or available > decision_at(origin)
                        or parse_month_label(proof["fit_information_end"][h]) > add_months(past, -1)
                        or fit_stamp.tzinfo is None or fit_stamp > decision_at(past)):
                    raise LeakageError("OOF publication or fit proof failed")
            eligible.add(past)
        # Only fully mature, requested proof rows may now decode numeric values.
        # These values serve the frozen pool hash and are never exported to policy.
        for proof in pool:
            for key in ("point_predictions", "actual_prices", "errors", "ratios"):
                proof[key] = [float(v) for v in proof[key]]
        pool_hash = hashlib.sha256(json.dumps(pool, sort_keys=True).encode()).hexdigest()
        if pool_hash != bundle.pool_sha256:
            raise ValueError("OOF pool hash mismatch")
        if any(p.source_oof_origin not in eligible for p in bundle.paths):
            raise LeakageError("Scenario draw is outside its complete mature OOF pool")
        return bundle.for_policy(origin)
