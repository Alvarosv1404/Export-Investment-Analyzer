"""Indicadores de inversion, analisis de sensibilidad y riesgo."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np

from .financials import ProjectInputs, ProjectOutputs, build_cashflows

_SENSITIVITY_LABELS = {
    "fob_price_shift": "Precio FOB",
    "capex_shift": "Inversión inicial",
    "volume_shift": "Volumen exportado",
    "cost_shift": "Costo variable unitario",
}


def summarize(outputs: ProjectOutputs, inputs: ProjectInputs) -> dict:
    """Resume los indicadores financieros y su lectura para la decision."""
    irr_pct = _percent(outputs.irr)
    return {
        "npv_usd": round(outputs.npv, 2),
        "irr_pct": irr_pct,
        "payback_years": (
            round(outputs.payback_years, 2) if outputs.payback_years is not None else None
        ),
        "discount_rate_pct": round(inputs.discount_rate * 100, 2),
        "initial_outflow_usd": round(outputs.cashflows[0], 2),
        "total_fcf_usd": round(sum(outputs.annual_fcf), 2),
        "roi_unlevered_pct": (
            round(sum(outputs.annual_fcf) / inputs.capex_usd * 100, 2)
            if inputs.capex_usd
            else None
        ),
        "verdict": _verdict(outputs, inputs),
    }


def _percent(value: float | None) -> float | None:
    return round(value * 100, 2) if value is not None else None


def _verdict(outputs: ProjectOutputs, inputs: ProjectInputs) -> dict[str, str]:
    if outputs.npv > 0 and outputs.irr is not None and outputs.irr > inputs.discount_rate:
        return {
            "label": "Favorable",
            "detail": "El proyecto crea valor por encima del costo de capital con estos supuestos.",
        }
    if outputs.npv > 0:
        return {
            "label": "Marginal",
            "detail": "El VAN es positivo, pero la TIR no supera el costo de capital.",
        }
    if outputs.payback_years is None:
        return {
            "label": "No se recupera",
            "detail": "El flujo no recupera la inversión dentro del horizonte del proyecto.",
        }
    return {
        "label": "No favorable",
        "detail": "El VAN es negativo: el proyecto destruye valor con estos supuestos.",
    }


def _with(inputs: ProjectInputs, **changes: object) -> ProjectInputs:
    """Crea un escenario sin modificar los supuestos del caso base."""
    return replace(inputs, **changes)


def _apply(inputs: ProjectInputs, variable: str, value: float) -> ProjectInputs | None:
    """Aplica al modelo un escenario de sensibilidad configurado."""
    if variable == "fob_price_shift":
        price = inputs.fob_price_usd_per_kg * (1 + value)
        return _with(inputs, fob_price_usd_per_kg=price) if price > 0 else None

    if variable == "capex_shift":
        factor = 1 + value
        if factor <= 0:
            return None
        return _with(
            inputs,
            capex_usd=inputs.capex_usd * factor,
            working_capital_usd=inputs.working_capital_usd * factor,
        )

    if variable == "volume_shift":
        factor = 1 + value
        if factor <= 0:
            return None
        ramp = [min(1.0, max(0.0, utilization * factor)) for utilization in inputs.utilization_ramp]
        return _with(inputs, utilization_ramp=ramp) if any(ramp) else None

    if variable == "cost_shift":
        factor = 1 + value
        if factor <= 0:
            return None
        return _with(
            inputs,
            purchase_cost_usd_per_kg=inputs.purchase_cost_usd_per_kg * factor,
            variable_cost_usd_per_kg=inputs.variable_cost_usd_per_kg * factor,
        )

    return None


def run_sensitivity(inputs: ProjectInputs, grid: dict[str, list[float]]) -> dict:
    """Calcula extremos de VAN al variar cada supuesto por separado."""
    base = build_cashflows(inputs)
    results: dict[str, list[dict]] = {}
    tornado = []

    for variable, values in grid.items():
        rows = []
        for value in values:
            scenario = _apply(inputs, variable, value)
            if scenario is None:
                continue
            output = build_cashflows(scenario)
            rows.append(
                {
                    "value": value,
                    "npv_usd": round(output.npv, 2),
                    "delta_npv_usd": round(output.npv - base.npv, 2),
                    "irr_pct": _percent(output.irr),
                }
            )
        if not rows:
            continue

        results[variable] = rows
        low = min(rows, key=lambda row: row["npv_usd"])
        high = max(rows, key=lambda row: row["npv_usd"])
        tornado.append(
            {
                "variable": variable,
                "label": _SENSITIVITY_LABELS.get(variable, variable.replace("_", " ").capitalize()),
                "low_npv_usd": low["npv_usd"],
                "high_npv_usd": high["npv_usd"],
                "low_delta_npv_usd": round(low["npv_usd"] - base.npv, 2),
                "high_delta_npv_usd": round(high["npv_usd"] - base.npv, 2),
                "swing_usd": round(high["npv_usd"] - low["npv_usd"], 2),
            }
        )

    tornado.sort(key=lambda row: row["swing_usd"], reverse=True)
    return {
        "base_npv_usd": round(base.npv, 2),
        "base_irr_pct": _percent(base.irr),
        "by_variable": results,
        "tornado": tornado,
        "most_sensitive": tornado[0]["variable"] if tornado else None,
        "most_sensitive_label": tornado[0]["label"] if tornado else None,
    }


def _bisect(
    func: Callable[[float], float],
    low: float,
    high: float,
    tolerance: float = 0.001,
    iterations: int = 60,
) -> float:
    """Busca una raiz de una funcion creciente acotada."""
    low_value = func(low)
    high_value = func(high)
    if low_value >= 0:
        return low
    if high_value <= 0:
        return high

    for _ in range(iterations):
        middle = (low + high) / 2
        if func(middle) >= 0:
            high = middle
        else:
            low = middle
        if high - low < tolerance:
            break
    return (low + high) / 2


def breakeven(inputs: ProjectInputs) -> dict:
    """Encuentra precio FOB y utilizacion que llevan el VAN aproximadamente a cero."""
    base = build_cashflows(inputs)
    if base.npv <= 0:
        return {"available": False}

    def npv_at_price(price: float) -> float:
        return build_cashflows(_with(inputs, fob_price_usd_per_kg=price)).npv

    base_utilization = inputs.utilization_ramp[0] if inputs.utilization_ramp else 1.0

    def npv_at_utilization(scale: float) -> float:
        ramp = [min(1.0, utilization * scale) for utilization in inputs.utilization_ramp]
        return build_cashflows(_with(inputs, utilization_ramp=ramp)).npv

    price_floor = _bisect(npv_at_price, 0.01, max(inputs.fob_price_usd_per_kg * 4, 1.0))
    utilization_scale = _bisect(npv_at_utilization, 0.0, 1.5)
    return {
        "available": True,
        "fob_price_floor_usd_per_kg": round(price_floor, 4),
        "utilization_floor_pct": round(min(1.0, base_utilization * utilization_scale) * 100, 2),
    }


# Amplitud del estres de los escenarios combinados. No es un supuesto del
# negocio (esos viven en config/), sino cuanto se mueven todas las palancas a
# la vez: el tornado mueve una variable por vez, esto las mueve todas juntas
# para poder leer tres bandas.
_SCENARIO_SHIFT = 0.15


def _scenario_inputs(inputs: ProjectInputs, sign: int, shift: float) -> ProjectInputs | None:
    """Caso base (sign=0), pesimista (sign=-1) u optimista (sign=+1).

    El pesimista baja precio y volumen y sube costos y CAPEX; el optimista hace
    lo contrario. Base no toca nada.
    """
    if sign == 0:
        return inputs

    price = inputs.fob_price_usd_per_kg * (1 + sign * shift)
    if price <= 0:
        return None
    return _with(
        inputs,
        fob_price_usd_per_kg=price,
        purchase_cost_usd_per_kg=inputs.purchase_cost_usd_per_kg * (1 - sign * shift),
        variable_cost_usd_per_kg=inputs.variable_cost_usd_per_kg * (1 - sign * shift),
        capex_usd=inputs.capex_usd * (1 - sign * shift),
        working_capital_usd=inputs.working_capital_usd * (1 - sign * shift),
        utilization_ramp=[
            min(1.0, max(0.0, utilization * (1 + sign * shift)))
            for utilization in inputs.utilization_ramp
        ],
    )


def run_scenarios(inputs: ProjectInputs, shift: float = _SCENARIO_SHIFT) -> dict:
    """Tres escenarios combinados (pesimista, base, optimista) con cifras reales.

    Cada numero sale de `build_cashflows`, igual que el resto del reporte: no hay
    valores escritos a mano. El frontend solo formatea lo que devuelve esto.
    """
    items: list[dict] = []
    for sign in (-1, 0, 1):
        scenario_inputs = _scenario_inputs(inputs, sign, shift)
        if scenario_inputs is None:
            continue
        output = build_cashflows(scenario_inputs)
        items.append(
            {
                "key": {-1: "pessimistic", 0: "base", 1: "optimistic"}[sign],
                "label": {-1: "Pesimista", 0: "Base", 1: "Optimista"}[sign],
                "npv_usd": round(output.npv, 2),
                "irr_pct": _percent(output.irr),
                "payback_years": (
                    round(output.payback_years, 2)
                    if output.payback_years is not None
                    else None
                ),
                "roi_pct": (
                    round(sum(output.annual_fcf) / scenario_inputs.capex_usd * 100, 2)
                    if scenario_inputs.capex_usd
                    else None
                ),
            }
        )
    return {
        "shift_pct": round(shift * 100, 2),
        "note": (
            "Escenarios combinados: \u00b1%.0f%% en precio FOB, costo de compra, "
            "costo variable, CAPEX y volumen al mismo tiempo. El tornado de arriba "
            "mueve una variable por vez; esto las mueve juntas." % (shift * 100)
        ),
        "items": items,
    }


def run_monte_carlo(
    inputs: ProjectInputs,
    price_volatility: float,
    variable_cost_volatility: float,
    volume_volatility: float,
    n_simulations: int = 2_000,
    seed: int = 42,
) -> dict:
    """Simula VAN con variaciones lognormales e independientes de precio, costo y volumen."""
    volatilities = (price_volatility, variable_cost_volatility, volume_volatility)
    if n_simulations <= 0:
        raise ValueError("El número de simulaciones debe ser mayor que cero.")
    if any(not np.isfinite(value) or value < 0 for value in volatilities):
        raise ValueError("Las volatilidades deben ser números finitos no negativos.")

    rng = np.random.default_rng(seed)

    def factors(coefficient_of_variation: float) -> np.ndarray:
        if coefficient_of_variation == 0:
            return np.ones(n_simulations)
        sigma = np.sqrt(np.log1p(coefficient_of_variation**2))
        return rng.lognormal(-0.5 * sigma**2, sigma, n_simulations)

    price_factors = factors(price_volatility)
    cost_factors = factors(variable_cost_volatility)
    volume_factors = factors(volume_volatility)
    npvs = []

    for price_factor, cost_factor, volume_factor in zip(
        price_factors, cost_factors, volume_factors, strict=True
    ):
        scenario = _with(
            inputs,
            fob_price_usd_per_kg=inputs.fob_price_usd_per_kg * float(price_factor),
            purchase_cost_usd_per_kg=inputs.purchase_cost_usd_per_kg * float(cost_factor),
            variable_cost_usd_per_kg=inputs.variable_cost_usd_per_kg * float(cost_factor),
            utilization_ramp=[
                min(1.0, utilization * float(volume_factor))
                for utilization in inputs.utilization_ramp
            ],
        )
        npvs.append(build_cashflows(scenario).npv)

    values = np.asarray(npvs)
    counts, edges = np.histogram(values, bins=12)
    histogram = [
        {
            "bin_start": round(float(edges[index]), 1),
            "bin_end": round(float(edges[index + 1]), 1),
            "label": f"${edges[index]:,.0f} a ${edges[index + 1]:,.0f}",
            "count": int(counts[index]),
            "is_negative": bool(edges[index] < 0),
        }
        for index in range(len(counts))
    ]
    prob_loss = round(float(np.mean(values < 0)) * 100, 1)

    return {
        "n_simulations": n_simulations,
        "assumptions": {
            "price_volatility_pct": round(price_volatility * 100, 2),
            "variable_cost_volatility_pct": round(variable_cost_volatility * 100, 2),
            "volume_volatility_pct": round(volume_volatility * 100, 2),
            "distribution": "lognormal",
            "independent_variables": True,
        },
        "prob_loss_pct": prob_loss,
        "prob_profit_pct": round(100 - prob_loss, 1),
        "npv_mean_usd": round(float(np.mean(values)), 2),
        "npv_median_usd": round(float(np.median(values)), 2),
        "npv_std_usd": round(float(np.std(values)), 2),
        "npv_p10_usd": round(float(np.percentile(values, 10)), 2),
        "npv_p90_usd": round(float(np.percentile(values, 90)), 2),
        "histogram": histogram,
        "verdict": "Riesgo bajo" if prob_loss < 20 else "Riesgo medio" if prob_loss < 50 else "Riesgo alto",
    }
