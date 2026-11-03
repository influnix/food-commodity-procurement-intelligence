"""Month-level synthetic engine: receive, serve, dispose, accrue, then order."""

from dataclasses import asdict, dataclass
from datetime import date
import math
from typing import Callable

from food_procurement_intelligence.evaluation.splits import add_months, decision_at, months_between
from .contracts import DecisionContext, OpeningOrder, PublicOrder, SimulationSettings, Supplier, ToyWorld


@dataclass(frozen=True)
class _ScheduledOrder:
    order_id: str
    supplier_id: str
    order_month: date
    promised_month: date
    actual_arrival: date
    quantity_tonnes: float

    def public(self, origin: date) -> PublicOrder:
        return PublicOrder(self.order_id, self.supplier_id, self.order_month, self.promised_month,
                           self.quantity_tonnes, self.promised_month <= origin)


def run_simulation(world: ToyWorld, settings: SimulationSettings, suppliers: tuple[Supplier, ...],
                   policy: Callable, initial_pipeline: tuple[OpeningOrder, ...] = ()) -> dict:
    catalogue = {s.supplier_id: s for s in suppliers}
    if not catalogue or len(catalogue) != len(suppliers):
        raise ValueError("Supplier IDs must be unique")
    delays = {(s, m): d for s, m, d in world.delays}
    if any(s not in catalogue or d > catalogue[s].maximum_delay_months for (s, _), d in delays.items()):
        raise ValueError("External delay violates a supplier's declared maximum")
    prices = {p.month: p for p in world.prices}
    demands = dict(world.realized_demands)
    outstanding, known_ids, orders, receipts, ledger = [], set(), [], [], []
    cohort_quantities = {}

    def schedule(order: OpeningOrder, initial: bool) -> None:
        if order.order_id in known_ids or order.supplier_id not in catalogue:
            raise ValueError("Duplicate order ID or unknown supplier")
        supplier = catalogue[order.supplier_id]
        supplier.validate_quantity(order.quantity_tonnes)
        key = order.supplier_id, order.order_month
        cohort_quantities[key] = cohort_quantities.get(key, 0.0) + order.quantity_tonnes
        if cohort_quantities[key] > supplier.monthly_capacity_tonnes + 1e-9:
            raise ValueError("Aggregate supplier monthly order capacity exceeded")
        promised = add_months(order.order_month, supplier.lead_time_months)
        actual = add_months(promised, delays.get(key, supplier.nominal_delay_months))
        latest = add_months(promised, supplier.maximum_delay_months)
        if latest > world.end or actual < world.start:
            raise ValueError("Terminal/opening pipeline violates the closed evaluation window")
        if initial and order.order_month >= world.start:
            raise ValueError("Opening pipeline must have been ordered before the simulation")
        if not initial and not world.start <= order.order_month <= world.end:
            raise ValueError("New order outside the decision calendar")
        known_ids.add(order.order_id)
        outstanding.append(_ScheduledOrder(order.order_id, order.supplier_id, order.order_month,
                                            promised, actual, order.quantity_tonnes))
        orders.append({**asdict(order), "promised_month": promised, "initial_pipeline": initial})

    for order in initial_pipeline:
        schedule(order, True)
    inventory = settings.initial_inventory_tonnes
    for month in months_between(world.start, world.end):
        opening, opening_pipeline = inventory, math.fsum(o.quantity_tonnes for o in outstanding)
        arrivals = [o for o in outstanding if o.actual_arrival == month]
        outstanding = [o for o in outstanding if o.actual_arrival != month]
        received = math.fsum(o.quantity_tonnes for o in arrivals)
        procurement, transport = 0.0, 0.0
        for order in arrivals:
            supplier = catalogue[order.supplier_id]
            market = prices[month].price
            unit_cost = market * (1 + supplier.price_premium)
            procurement += unit_cost * order.quantity_tonnes
            transport += supplier.unit_transport_cost * order.quantity_tonnes
            receipts.append({"order_id": order.order_id, "supplier_id": order.supplier_id, "order_month": order.order_month,
                "promised_month": order.promised_month, "receipt_month": month, "quantity_tonnes": order.quantity_tonnes,
                "market_price": market, "unit_procurement_cost": unit_cost,
                "procurement_cost": unit_cost * order.quantity_tonnes,
                "transport_cost": supplier.unit_transport_cost * order.quantity_tonnes,
                "cost_recognized_at": decision_at(month).isoformat(), "price_available_at": prices[month].available_at.isoformat()})
        available, demand = opening + received, demands[month]
        fulfilled = min(available, demand)
        unmet = demand - fulfilled
        disposal = max(available - fulfilled - settings.warehouse_capacity_tonnes, 0.0)
        inventory = available - fulfilled - disposal
        if inventory < 0 or not math.isclose(opening + received, fulfilled + disposal + inventory, abs_tol=1e-9):
            raise ArithmeticError("Inventory conservation or nonnegativity violated")
        published = tuple(p for p in world.prices if p.month <= add_months(month, -1) and p.available_at <= decision_at(month))
        context = DecisionContext(month, world.end, inventory, settings.planned_demand_tonnes, suppliers,
                                  tuple(o.public(month) for o in outstanding), published)
        requests = tuple(policy(context))
        new_orders = []
        for index, request in enumerate(requests):
            order = OpeningOrder(f"{month:%Y-%m}|{request.supplier_id}|{index}", request.supplier_id, month, request.quantity_tonnes)
            schedule(order, False)
            new_orders.append(order)
        terminal = settings.terminal_usd_per_tonne_deviation * abs(inventory - settings.terminal_target_tonnes) if month == world.end else 0.0
        components = {"procurement_cost": procurement, "transport_cost": transport,
                      "holding_cost": inventory * settings.holding_usd_per_tonne_month,
                      "unmet_cost": unmet * settings.unmet_usd_per_tonne,
                      "disposal_cost": disposal * settings.disposal_usd_per_tonne,
                      "terminal_cost": terminal}
        closing_pipeline = math.fsum(o.quantity_tonnes for o in outstanding)
        if not math.isclose(opening_pipeline + math.fsum(o.quantity_tonnes for o in new_orders), received + closing_pipeline, abs_tol=1e-9):
            raise ArithmeticError("Order pipeline quantity is not conserved")
        ledger.append({"scenario_id": world.scenario_id, "month": month, "beginning_inventory": opening,
            "beginning_outstanding_quantity": opening_pipeline, "received_quantity": received, "available_inventory": available,
            "realized_demand": demand, "fulfilled_demand": fulfilled, "unmet_demand": unmet,
            "disposed_quantity": disposal, "ending_inventory": inventory,
            "new_order_quantity": math.fsum(o.quantity_tonnes for o in new_orders),
            "new_orders": [asdict(o) for o in new_orders], "outstanding_quantity": closing_pipeline,
            "outstanding_orders": [asdict(o.public(month)) for o in outstanding],
            **components, "total_cost": math.fsum(components.values()),
            "unit_quantity": "metric_tonne", "unit_cost": "USD", "knowledge_type": world.knowledge_type})
    if outstanding:
        raise ValueError("Unvalued outstanding orders at the terminal boundary")
    totals = {name: math.fsum(row[name] for row in ledger) for name in (*components, "total_cost", "unmet_demand", "fulfilled_demand")}
    if len(receipts) != len(known_ids) or len({r["order_id"] for r in receipts}) != len(receipts):
        raise ArithmeticError("Missing or duplicate delivery")
    return {"ledger": ledger, "orders": orders, "receipts": receipts,
            "summary": {"scenario_id": world.scenario_id, **totals, "ending_inventory": inventory,
                        "terminal_outstanding_tonnes": 0.0, "initial_pipeline_tonnes": math.fsum(o.quantity_tonnes for o in initial_pipeline),
                        "initial_inventory_tonnes": settings.initial_inventory_tonnes,
                        "knowledge_type": world.knowledge_type}}
