"""Point-only saved validation adapter; never exports actual/error/score columns."""

import csv
import json
from pathlib import Path

from food_procurement_intelligence.evaluation.model_backtesting import digest
from food_procurement_intelligence.evaluation.splits import parse_month_label, decision_at, HoldoutLockedError, LeakageError
from food_procurement_intelligence.forecasting.common import ModelPrediction


class PointForecastAdapter:
    def __init__(self, points, plan, source_id: str):
        self._plan, self.source_id = plan, source_id
        self._values = {}
        for point in points:
            key = point.forecast_origin, point.horizon
            if key in self._values:
                raise ValueError("Duplicate point forecast key")
            if (not plan.validation_origin_start <= point.forecast_origin <= plan.validation_origin_end
                    or plan.target_partition(point.target_month) != "validation"):
                raise HoldoutLockedError("Adapter only accepts frozen validation forecast keys")
            self._values[key] = point

    def __call__(self, origin):
        if not self._plan.validation_origin_start <= origin <= self._plan.validation_origin_end:
            raise HoldoutLockedError("Holdout/non-validation forecast access is prohibited")
        return tuple(self._values[(origin, h)] for h in (1, 2, 3))


def load_point_adapter(directory: Path, plan, expected_model: str) -> PointForecastAdapter:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["holdout_locked"] is not True:
        raise HoldoutLockedError("Source artifact was not holdout locked")
    for name, expected in manifest["output_sha256"].items():
        if digest(directory / name) != expected:
            raise ValueError("Saved Day 4 forecast artifact changed")
    points = []
    with (directory / "predictions.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            origin = parse_month_label(row["forecast_origin"])
            if row["model_name"] != expected_model or row["forecast_asof_at"] != decision_at(origin).isoformat():
                raise LeakageError("Forecast model/issue clock differs from the selected origin")
            points.append(ModelPrediction(origin, parse_month_label(row["information_cutoff"]),
                parse_month_label(row["target_month"]), int(row["horizon"]), float(row["predicted_price"]), row["model_name"], row["unit"]))
    return PointForecastAdapter(tuple(points), plan, digest(directory / "manifest.json"))
