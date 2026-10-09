"""VAN, TIR, payback y analisis de sensibilidad.

Lo que hace un buen analisis de sensibilidad y casi nadie hace bien: no prueba
"el escenario optimista" y "el pesimista" con dos números inventados, sino que
mueve UNA variable a la vez y mide cuanto se mueve el VAN. Eso produce un
tornado, que si ordena las variables te dice en que supuesto conviene invertir
el esfuerzo de negociacion.
"""

from __future__ import annotations

from dataclasses import replace

from .financials import ProjectInputs, ProjectOutputs, build_cashflows


def summarize(outputs: ProjectOutputs, inputs: ProjectInputs) -> dict:
    """Indicadores de retorno de la decision de inversion."""
    def pct(value: float | None) -> float | None:
        return round(value * 100, 2) if value is not None else None

    return {
        "npv_usd": round(outputs.npv, 2),
        "irr_pct": pct(outputs.irr),
        "payback_years": (
            round(outputs.payback_years, 2) if outputs.payback_years is not None else None
        ),
        "discount_rate_pct": pct(inputs.discount_rate),
        "initial_outflow_usd": round(outputs.cashflows[0], 2),
        "total_fcf_usd": round(sum(outputs.annual_fcf), 2),
        "roi_unlevered_pct": (
            round(sum(outputs.annual_fcf) / inputs.capex_usd * 100, 2) if inputs.capex_usd else None
        ),
        "verdict": _verdict(outputs, inputs),
    }


def _verdict(outputs: ProjectOutputs, inputs: ProjectInputs) -> dict:
    """Lectura del resultado, en el lenguaje de una comision de inversion."""
    if outputs.npv > 0 and outputs.irr and outputs.irr > inputs.discount_rate:
        return {
            "label": "Favorable",
            "detail": "El proyecto crea valor sobre el costo de capital con estos supuestos.",
        }
    if outputs.npv > 0:
        return {
            "label": "Marginal",
            "detail": (
                "El VAN es positivo pero la TIR no supera el costo de capital. "
                "Revisar supuestos de precio, volumen o CAPEX antes de decidir."
            ),
        }
    if outputs.payback_years is None:
        return {
            "label": "No se recupera",
            "detail": (
                "El flujo no vuelve a positivo dentro del horizonte. Con estos "
                "supuestos no hay caso; el problema es el negocio, no la tasa."
            ),
        }
    return {
        "label": "No favorable",
        "detail": "VAN negativo. El proyecto destruye valor con estos supuestos.",
    }


def _with(inputs: ProjectInputs, **changes) -> ProjectInputs:
    return replace(inputs, **changes)


def run_sensitivity(inputs: ProjectInputs, grid: dict[str, list[float]]) -> dict:
    """Tornado: mueve una variable a la vez y mide el efecto en el VAN.

    grid viene de config/assumptions.yaml (seccion `sensitivity`).
    Cada valor es un CAMBIO RELATIVO o un valor absoluto segun la variable;
    ver _apply. El escenario base se incluye siempre.
    """
    base = build_cashflows(inputs)
    base_npv = base.npv

    results: dict[str, list[dict]] = {}

    for variable, values in grid.items():
        rows = []
        for value in values:
            scenario = _apply(inputs, variable, value)
            if scenario is None:
                continue
            out = build_cashflows(scenario)
            rows.append(
                {
                    "value": value,
                    "npv_usd": round(out.npv, 2),
                    "delta_npv_usd": round(out.npv - base_npv, 2),
                    "irr_pct": round(out.irr * 100, 2) if out.irr is not None else None,
                }
            )
        if rows:
            results[variable] = rows

    # Tornado:variables ordenadas por cuanto mueven el VAN en el peor caso.
    impact = [
        {
            "variable": variable,
            "swing_usd": round(
                max(abs(r["delta_npv_usd"]) for r in rows)
                - min(abs(r["delta_npv_usd"]) for r in rows),
                2,
            ),
        }
        for variable, rows in results.items()
    ]
    impact.sort(key=lambda x: x["swing_usd"], reverse=True)

    return {
        "base_npv_usd": round(base_npv, 2),
        "base_irr_pct": round(base.irr * 100, 2) if base.irr is not None else None,
        "by_variable": results,
        "tornado": impact,
        "most_sensitive": impact[0]["variable"] if impact else None,
    }


def _apply(inputs: ProjectInputs, variable: str, value: float) -> ProjectInputs | None:
    """Aplica un valor de sensibilidad. Devuelve None si la variable no existe."""
    if variable == "discount_rate":
        return _with(inputs, discount_rate=value)
    if variable == "fob_price_shift":
        price = inputs.fob_price_usd_per_kg * (1 + value)
        if price <= 0:
            return None
        return _with(inputs, fob_price_usd_per_kg=price)
    if variable == "fx_shift":
        return _with(inputs, fob_price_usd_per_kg=inputs.fob_price_usd_per_kg * (1 + value))
    if variable == "capex_shift":
        return _with(
            inputs,
            capex_usd=inputs.capex_usd * (1 + value),
            working_capital_usd=inputs.working_capital_usd * (1 + value),
        )
    if variable == "volume_shift":
        # Mueve la rampa de ocupacion proporcionalmente.
        ramp = [min(1.0, max(0.0, u * (1 + value))) for u in inputs.utilization_ramp]
        if max(ramp) <= 0:
            return None
        return _with(inputs, utilization_ramp=ramp)
    if variable == "cost_shift":
        return _with(
            inputs,
            variable_cost_usd_per_kg=inputs.variable_cost_usd_per_kg * (1 + value),
            purchase_cost_usd_per_kg=inputs.purchase_cost_usd_per_kg * (1 + value),
        )
    return None


def breakeven(inputs: ProjectInputs) -> dict:
    """Punto de equilibrio de las dos variables que casi siempre deciden el caso.

    1. VAN = 0 -> que precio FOB minimo hace viable el proyecto.
    2. VAN = 0 -> que ocupacion de planta minima hace viable el proyecto.
    """
    base = build_cashflows(inputs)
    if base.npv <= 0:
        return {
            "available": False,
            "reason": "El escenario base ya tiene VAN negativo: no hay un precio minimo que lo salve.",
        }

    def npv_at_price(price: float) -> float:
        return build_cashflows(_with(inputs, fob_price_usd_per_kg=price)).npv

    def npv_at_utilization(scale: float) -> float:
        ramp = [min(1.0, u * scale) for u in inputs.utilization_ramp]
        return build_cashflows(_with(inputs, utilization_ramp=ramp)).npv

    return {
        "available": True,
        "fob_price_floor_usd_per_kg": _bisect(npv_at_price, 0.01, inputs.fob_price_usd_per_kg * 4),
        "utilization_floor_pct": _bisect(npv_at_utilization, 0.05, 1.5) * 100,
        "current_fob_price_usd_per_kg": inputs.fob_price_usd_per_kg,
        "note": "Valores por debajo de estos umbrales hacen el VAN negativo.",
    }


def _bisect(func, low: float, high: float, tolerance: float = 0.001, iterations: int = 60) -> float:
    """Busqueda por biseccion de la raiz de func ( VAN = 0 ).

    Espera una funcion CRECIENTE, que es el caso de los dos umbrales que se
    calculan: subir el precio FOB sube el VAN, y subir la ocupacion tambien.
    Con esa convencion, si f(mid) > 0 la raiz esta POR DEBAJO de mid, asi que
    el extremo que se mueve es `high`. Invertirlo devuelve el techo del rango
    de busqueda en vez del umbral, que es un numero plausible y por lo tanto
    peligroso.
    """
    if func(low) > 0:
        return low
    if func(high) < 0:
        return high
    for _ in range(iterations):
        mid = (low + high) / 2
        if func(mid) > 0:
            high = mid
        else:
            low = mid
        if high - low < tolerance:
            break
    return (low + high) / 2
