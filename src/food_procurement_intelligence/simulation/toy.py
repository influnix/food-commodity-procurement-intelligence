"""Explicit synthetic worlds and hand-calculated expectations, not observed prices."""

from datetime import datetime

from food_procurement_intelligence.data.availability import VisiblePrice
from food_procurement_intelligence.data.world_bank import assumed_available_at
from food_procurement_intelligence.evaluation.splits import add_months, months_between, parse_month_label
from .contracts import OpeningOrder, SimulationSettings, Supplier, ToyWorld


HAND_EXPECTED = {
    "A_normal": {"procurement_cost": 43440., "holding_cost": 1860., "unmet_demand": 0., "unmet_cost": 0., "terminal_cost": 1620., "total_cost": 46920.},
    "B_delay": {"procurement_cost": 43440., "holding_cost": 1620., "unmet_demand": 0., "unmet_cost": 0., "terminal_cost": 1620., "total_cost": 46680.},
    "C_demand_spike": {"procurement_cost": 43440., "holding_cost": 720., "unmet_demand": 180., "unmet_cost": 270000., "terminal_cost": 1800., "total_cost": 315960.},
    "D_price_rise": {"procurement_cost": 69240., "holding_cost": 1860., "unmet_demand": 0., "unmet_cost": 0., "terminal_cost": 1620., "total_cost": 72720.},
    "E_combined": {"procurement_cost": 73320., "holding_cost": 1200., "unmet_demand": 180., "unmet_cost": 270000., "terminal_cost": 1800., "total_cost": 346320.},
}


def toy_inputs(config: dict):
    simulation = config["simulation"]
    settings = SimulationSettings(**{key: simulation[key] for key in SimulationSettings.__dataclass_fields__})
    suppliers = tuple(Supplier(**row) for row in config["suppliers"])
    start, end = parse_month_label(simulation["toy_start"]), parse_month_label(simulation["toy_end"])
    months = months_between(start, end)
    if len(months) != 6 or not simulation["toy_initial_pipeline"]:
        raise ValueError("The Day 6 hand-check uses the frozen six-month opening-pipeline Toy")
    initial = (OpeningOrder("opening_A", "A", add_months(start, -1), 80.),
               OpeningOrder("opening_B", "B", add_months(start, -1), 20.))
    worlds = []
    for scenario_id in HAND_EXPECTED:
        rise = scenario_id in ("D_price_rise", "E_combined")
        spike = scenario_id in ("C_demand_spike", "E_combined")
        delay = scenario_id in ("B_delay", "E_combined")
        prices = (100., 100., 150., 200., 200., 200.) if rise else (100.,) * 6
        previous = add_months(start, -1)
        observations = tuple(VisiblePrice(month, price, "USD_per_metric_tonne", datetime.fromisoformat(assumed_available_at(month)))
                             for month, price in ((previous, 100.), *zip(months, prices)))
        demands = tuple((month, 300. if spike and i == 2 else 100.) for i, month in enumerate(months))
        worlds.append(ToyWorld(scenario_id, start, end, observations, demands, (("A", start, 1),) if delay else ()))
    return settings, suppliers, initial, tuple(worlds)
