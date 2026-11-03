"""Units, synthetic supply terms and the narrow public decision context."""

from dataclasses import dataclass
from datetime import date
import math

from food_procurement_intelligence.data.availability import VisiblePrice, assert_feature_available
from food_procurement_intelligence.evaluation.splits import add_months, months_between


def nonnegative(value: float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    price_premium: float
    lead_time_months: int
    monthly_capacity_tonnes: float
    minimum_order_quantity: float = 0.0
    order_multiple: float = 0.0
    nominal_delay_months: int = 0
    maximum_delay_months: int = 1
    unit_transport_cost: float = 0.0

    def __post_init__(self) -> None:
        if not self.supplier_id or type(self.lead_time_months) is not int or self.lead_time_months < 1:
            raise ValueError("Supplier needs an ID and a positive integer monthly lead")
        if (type(self.maximum_delay_months) is not int or self.maximum_delay_months < 0
                or type(self.nominal_delay_months) is not int or not 0 <= self.nominal_delay_months <= self.maximum_delay_months):
            raise ValueError("Invalid declared delay support")
        for name in ("price_premium", "monthly_capacity_tonnes", "minimum_order_quantity", "order_multiple", "unit_transport_cost"):
            nonnegative(getattr(self, name), name)
        if self.monthly_capacity_tonnes <= 0 or self.minimum_order_quantity > self.monthly_capacity_tonnes:
            raise ValueError("Invalid capacity/MOQ")

    def validate_quantity(self, quantity: float) -> None:
        nonnegative(quantity, "order quantity")
        if quantity <= 0 or quantity > self.monthly_capacity_tonnes + 1e-9 or quantity < self.minimum_order_quantity:
            raise ValueError("Order violates positive quantity/capacity/MOQ")
        if self.order_multiple and not math.isclose(quantity / self.order_multiple, round(quantity / self.order_multiple), abs_tol=1e-9, rel_tol=0):
            raise ValueError("Order violates the required multiple")


@dataclass(frozen=True)
class SimulationSettings:
    planned_demand_tonnes: float
    initial_inventory_tonnes: float
    warehouse_capacity_tonnes: float
    holding_usd_per_tonne_month: float
    unmet_usd_per_tonne: float
    disposal_usd_per_tonne: float
    terminal_target_tonnes: float
    terminal_usd_per_tonne_deviation: float
    terminal_mode: str = "require_empty_pipeline_no_salvage"

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if name != "terminal_mode":
                nonnegative(getattr(self, name), name)
        if (self.warehouse_capacity_tonnes <= 0 or self.initial_inventory_tonnes > self.warehouse_capacity_tonnes
                or self.terminal_target_tonnes > self.warehouse_capacity_tonnes
                or self.terminal_mode != "require_empty_pipeline_no_salvage"):
            raise ValueError("Invalid inventory capacity or terminal accounting mode")


@dataclass(frozen=True)
class OrderRequest:
    supplier_id: str
    quantity_tonnes: float


@dataclass(frozen=True)
class OpeningOrder:
    order_id: str
    supplier_id: str
    order_month: date
    quantity_tonnes: float


@dataclass(frozen=True)
class PublicOrder:
    order_id: str
    supplier_id: str
    order_month: date
    promised_month: date
    quantity_tonnes: float
    overdue: bool


@dataclass(frozen=True)
class DecisionContext:
    origin: date
    simulation_end: date
    on_hand_tonnes: float
    planned_demand_tonnes: float
    suppliers: tuple[Supplier, ...]
    outstanding_orders: tuple[PublicOrder, ...]
    published_prices: tuple[VisiblePrice, ...]

    def __post_init__(self) -> None:
        nonnegative(self.on_hand_tonnes, "known on hand")
        nonnegative(self.planned_demand_tonnes, "demand plan")
        assert_feature_available([p.month for p in self.published_prices], self.origin,
                                 {p.month: p.available_at for p in self.published_prices})
        if any(o.order_month > self.origin or o.overdue != (o.promised_month <= self.origin) for o in self.outstanding_orders):
            raise ValueError("Invalid public pipeline status")


@dataclass(frozen=True)
class ToyWorld:
    scenario_id: str
    start: date
    end: date
    prices: tuple[VisiblePrice, ...]
    realized_demands: tuple[tuple[date, float], ...]
    delays: tuple[tuple[str, date, int], ...] = ()
    knowledge_type: str = "synthetic_toy_not_world_bank"

    def __post_init__(self) -> None:
        if self.knowledge_type != "synthetic_toy_not_world_bank" or not self.scenario_id or self.start > self.end:
            raise ValueError("Day 6 engine only accepts explicitly synthetic Toy inputs")
        expected = months_between(self.start, self.end)
        if tuple(m for m, _ in self.realized_demands) != expected:
            raise ValueError("Demand months must be unique, contiguous and ordered")
        price_map = {p.month: p for p in self.prices}
        if len(price_map) != len(self.prices) or any(m not in price_map for m in expected):
            raise ValueError("Missing/duplicate Toy price months")
        for p in self.prices:
            if (not math.isfinite(p.price) or p.price <= 0 or p.unit != "USD_per_metric_tonne"
                    or p.available_at.tzinfo is None or p.available_at.utcoffset() is None):
                raise ValueError("Invalid Toy price/unit/publication")
        for _, demand in self.realized_demands:
            nonnegative(demand, "realized demand")
        keys = [(s, m) for s, m, _ in self.delays]
        if len(keys) != len(set(keys)) or any(type(d) is not int or d < 0 for _, _, d in self.delays):
            raise ValueError("Duplicate/invalid exogenous supplier-order-month delay")
