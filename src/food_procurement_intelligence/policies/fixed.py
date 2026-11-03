"""Known-calendar fixed allocation; no future paths or evaluation seed argument."""

from dataclasses import dataclass
from food_procurement_intelligence.evaluation.splits import add_months
from food_procurement_intelligence.simulation.contracts import DecisionContext, OrderRequest


@dataclass(frozen=True)
class FixedProcurement:
    allocations: tuple[tuple[str, float], ...] = (("A", 80.0), ("B", 20.0))

    def __call__(self, context: DecisionContext) -> tuple[OrderRequest, ...]:
        if len({s for s, _ in self.allocations}) != len(self.allocations):
            raise ValueError("Duplicate supplier allocation")
        suppliers = {s.supplier_id: s for s in context.suppliers}
        requests = []
        for supplier_id, quantity in self.allocations:
            supplier = suppliers[supplier_id]
            supplier.validate_quantity(quantity)
            latest_arrival = add_months(context.origin, supplier.lead_time_months + supplier.maximum_delay_months)
            if latest_arrival <= context.simulation_end:
                requests.append(OrderRequest(supplier_id, quantity))
        return tuple(requests)
