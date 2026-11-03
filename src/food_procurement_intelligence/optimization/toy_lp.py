"""Five prespecified hand-verifiable LPs, unrelated to actual market prices."""

from datetime import date
from food_procurement_intelligence.evaluation.splits import add_months
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.simulation.contracts import Supplier, SimulationSettings, DecisionContext


def hand_problems():
    origin = date(2000, 1, 1)
    specifications = [
        ("A_single", 1, 2., (10.,), (Supplier("S", 0., 1, 100., maximum_delay_months=0),), 0., 80.),
        ("B_lead", 2, 0., (10., 10.), (Supplier("A", 0., 2, 10., maximum_delay_months=0), Supplier("B", .2, 1, 10., maximum_delay_months=0)), 1., 220.),
        ("C_capacity", 1, 0., (10.,), (Supplier("A", 0., 1, 4., maximum_delay_months=0), Supplier("B", .2, 1, 10., maximum_delay_months=0)), 0., 112.),
        ("D_hold_price", 2, 0., (10., 20.), (Supplier("S", 0., 1, 20., maximum_delay_months=0),), 1., 210.),
        ("E_shortage", 1, 0., (10.,), (Supplier("S", 0., 1, 4., maximum_delay_months=0),), 0., 6040.),
    ]
    result = []
    for name, horizon, inventory, prices, suppliers, holding, objective in specifications:
        settings = SimulationSettings(10., inventory, 100., holding, 1000., 1., 0., 0.)
        context = DecisionContext(origin, add_months(origin, horizon), inventory, 10., suppliers, (), ())
        points = tuple(ModelPrediction(origin, add_months(origin, -1), add_months(origin, h), h, price, "synthetic_hand_lp")
                       for h, price in enumerate(prices, 1))
        result.append((name, context, points, settings, objective))
    return result
