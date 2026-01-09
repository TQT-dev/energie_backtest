from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from .aggregates import PeriodKey, aggregate_costs
from .costs import total_cost
from .models import QuarterCost


@dataclass(frozen=True)
class CostReport:
    total_cost_eur: float
    reference_cost_eur: float
    difference_eur: float
    difference_pct: float
    aggregated_costs: Dict[PeriodKey, float]
    aggregated_reference_costs: Dict[PeriodKey, float]


def build_cost_report(
    costs: Iterable[QuarterCost],
    reference_price_eur_per_kwh: float,
    *,
    period: str = "month",
) -> CostReport:
    """Compare total cost to a reference price and aggregate by period."""

    costs_list = list(costs)
    total = total_cost(costs_list)
    reference_total = _reference_total(costs_list, reference_price_eur_per_kwh)
    difference = total - reference_total
    difference_pct = _difference_pct(reference_total, difference)

    aggregated_costs = aggregate_costs(costs_list, period=period)
    aggregated_reference_costs = _aggregate_reference_costs(
        costs_list, reference_price_eur_per_kwh, period
    )

    return CostReport(
        total_cost_eur=total,
        reference_cost_eur=reference_total,
        difference_eur=difference,
        difference_pct=difference_pct,
        aggregated_costs=aggregated_costs,
        aggregated_reference_costs=aggregated_reference_costs,
    )


def _reference_total(
    costs: Iterable[QuarterCost], reference_price_eur_per_kwh: float
) -> float:
    return sum(item.consumption_kwh * reference_price_eur_per_kwh for item in costs)


def _difference_pct(reference_total: float, difference: float) -> float:
    if reference_total == 0:
        return 0.0
    return (difference / reference_total) * 100.0


def _aggregate_reference_costs(
    costs: Iterable[QuarterCost],
    reference_price_eur_per_kwh: float,
    period: str,
) -> Dict[PeriodKey, float]:
    reference_costs = []
    for item in costs:
        reference_costs.append(
            QuarterCost(
                timestamp=item.timestamp,
                consumption_kwh=item.consumption_kwh,
                tariff_eur_per_kwh=reference_price_eur_per_kwh,
                total_cost_eur=item.consumption_kwh * reference_price_eur_per_kwh,
            )
        )
    return aggregate_costs(reference_costs, period=period)
