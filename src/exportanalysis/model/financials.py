"""Modelo financiero de la operacion de exportacion.

Como leerlo: este modelo NO predice. Traduce un supuesto de negocio a un flujo
de caja y te dice que valor tiene. Si el resultado es negativo, no dice "no
inviertas", dice "con estos supuestos no se justify". Cambiar supuestos y
volver a correr es el uso correcto.

Estructura de un ano tipo:
    volumen_kg  = capacidad * ocupacion  (con curva de aprendizaje)
    ingresos    = volumen * precio_FOB
    costo vars  = volumen * (compra + procesamiento)
    opex fijo   = planilla, alquiler, servicios
    EBIT        = ingresos - vars - fijos - depreciacion
    impuestos   = EBIT * tasa
    FCF         = EBIT - impuestos + depreciacion - Delta capital trabajo - CAPEX
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import numpy_financial as npf
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class ProjectInputs:
    """Supuestos resueltos de config/assumptions.yaml para un producto."""

    slug: str
    capacity_kg_year: float
    capex_usd: float
    variable_cost_usd_per_kg: float
    purchase_cost_usd_per_kg: float
    opex_fixed_usd_year: float
    working_capital_usd: float

    project_years: int = 5
    discount_rate: float = 0.12
    tax_rate: float = 0.30
    learning_rate: float = 0.03
    sales_commission: float = 0.05
    freight_pct_fob: float = 0.05
    compliance_pct_fct: float = 0.02
    wc_inventory_days: int = 60
    wc_receivable_days: int = 45
    wc_payable_days: int = 30
    depreciation_years: int = 10
    capex_schedule: list[float] = field(default_factory=lambda: [1.0])
    utilization_ramp: list[float] = field(default_factory=lambda: [0.3, 0.55, 0.75, 0.9, 0.95])

    # Parametros que vienen del analisis de mercado, no del config.
    fob_price_usd_per_kg: float = 4.0
    capture_share: float = 0.0  # fraccion del headroom de mercado que se apunta


@dataclass
class ProjectOutputs:
    npv: float
    irr: float | None
    payback_years: float | None
    total_capex: float
    terminal_value: float
    annual_fcf: list[float]
    cumulative_fcf: list[float]
    cashflows: list[float]


def _ramp(values: list[float], years: int) -> list[float]:
    """Extiende o recorta la curva de ocupacion a la cantidad de anos del proyecto."""
    if not values:
        return [1.0] * years
    if len(values) >= years:
        return list(values[:years])
    # Si el proyecto dura mas que la rampa, se queda en el ultimo valor.
    return list(values) + [values[-1]] * (years - len(values))


def _capex_schedule(values: list[float], years: int) -> list[float]:
    """Reparte el CAPEX entre t=0 y los anos de operacion.

    Devuelve una lista de `years + 1` posiciones: el indice 0 es el ano 0 (la
    inversion) y los indices 1..years son los anos de operacion.

    Lo que no este listado NO se gasta. No se estira el ultimo valor como se
    hace con la curva de ocupacion, porque repetir un CAPEX lo multiplica: un
    `capex_schedule: [1.0]` significa "todo el CAPEX en el ano 0" y nada mas.
    """
    if not values:
        return [1.0] + [0.0] * years
    out = list(values[: years + 1])
    out += [0.0] * (years + 1 - len(out))
    return out


def _learning_factor(rate: float, year_index: int) -> float:
    """Reduccion del costo unitario por curva de aprendizaje.

    Version lineal y auditable: el costo por kg baja `rate` por cada ano de
    operacion, con un piso del 50% del costo inicial para que la curva no se
    vuelva una fuente oculta de profitability.

    Una curva de aprendizaje real se indexa a la produccion acumulada, no al
    ano. Si tienes el volumen historico, cambia esta funcion por esa version:
    es una de las palancas mas fuertes del modelo y conviene que sea explicita.
    """
    return max(0.5, (1 - rate) ** year_index)


def build_cashflows(inputs: ProjectInputs) -> ProjectOutputs:
    """Construye la lista de flujos: ano 0 (inversion) + anos 1..N."""
    years = inputs.project_years
    utilization = _ramp(inputs.utilization_ramp, years)
    # Indice 0 = ano 0. Asi el CAPEX del ano 0 no vuelve a descontarse dentro
    # del FCF del ano 1, que es donde se.contaba dos veces.
    schedule = _capex_schedule(inputs.capex_schedule, years)
    scheduled = sum(schedule)
    if abs(scheduled - 1.0) > 1e-6:
        log.warning(
            "capex_schedule suma %.3f y no 1.0: el CAPEX se reparte en una "
            "fraccion distinta a la prevista. Revisa config/assumptions.yaml.",
            scheduled,
        )

    annual_fcf: list[float] = []
    for index in range(years):
        volume = inputs.capacity_kg_year * utilization[index]

        learning = _learning_factor(inputs.learning_rate, index)
        unit_purchase = inputs.purchase_cost_usd_per_kg * learning
        unit_variable = inputs.variable_cost_usd_per_kg * learning

        revenue = volume * inputs.fob_price_usd_per_kg
        commission = revenue * inputs.sales_commission
        compliance = revenue * inputs.compliance_pct_fct

        variable_costs = volume * (unit_purchase + unit_variable)
        fixed_costs = inputs.opex_fixed_usd_year

        depreciation = (
            inputs.capex_usd / inputs.depreciation_years
            if index < inputs.depreciation_years
            else 0.0
        )
        # schedule[index + 1]: el CAPEX del anio de operacion `index + 1`. El
        # del ano 0 se descuenta en el flujo inicial, no aqui.
        capex = inputs.capex_usd * schedule[index + 1]

        ebit = revenue - variable_costs - fixed_costs - commission - compliance - depreciation
        taxable = max(0.0, ebit)
        taxes = taxable * inputs.tax_rate

        wc_ratio = (
            inputs.wc_inventory_days + inputs.wc_receivable_days - inputs.wc_payable_days
        ) / 365.0
        working_capital = volume * inputs.fob_price_usd_per_kg * wc_ratio

        # El capital de trabajo inicial es una salida del ano 0. Despues se
        # mueve con el volumen: cada delta es la variacion contra el ano previo.
        if index == 0:
            delta_wc = -inputs.working_capital_usd
        else:
            prev_volume = inputs.capacity_kg_year * utilization[index - 1]
            prev_wc = prev_volume * inputs.fob_price_usd_per_kg * wc_ratio
            delta_wc = working_capital - prev_wc

        fcf = ebit - taxes + depreciation - capex + delta_wc
        annual_fcf.append(fcf)

    # El ano 0 financia el CAPEX programado para ese ano mas el capital de
    # trabajo inicial. El delta de capital de trabajo de cada ano va dentro del
    # FCF, para no descontarlo dos veces.
    cashflows = [
        -(inputs.capex_usd * schedule[0] + inputs.working_capital_usd),
        *annual_fcf,
    ]

    npv = float(npf.npv(inputs.discount_rate, cashflows))

    # npf.irr devuelve nan cuando no converge (flujo que nunca cambia de signo).
    # Eso no es lo mismo que "TIR = 0": se traduce a None para que la UI pueda
    # distinguir "no hay TIR" de "TIR cero".
    try:
        raw_irr = float(npf.irr(cashflows))
    except (ValueError, ZeroDivisionError):
        raw_irr = float("nan")
    irr = raw_irr if np.isfinite(raw_irr) else None

    cumulative: list[float] = []
    running = 0.0
    for flow in cashflows:
        running += flow
        cumulative.append(running)

    payback = None
    for i in range(1, len(cumulative)):
        if cumulative[i] >= 0:
            prev = cumulative[i - 1]
            if i == 0 or prev == cumulative[i]:
                payback = float(i)
            else:
                fraction = abs(prev) / abs(cumulative[i] - prev)
                payback = float(i - 1) + fraction
            break

    return ProjectOutputs(
        npv=npv,
        irr=irr,
        payback_years=payback,
        total_capex=inputs.capex_usd,
        terminal_value=0.0,
        annual_fcf=annual_fcf,
        cumulative_fcf=cumulative,
        cashflows=cashflows,
    )


def annual_pnl(inputs: ProjectInputs) -> pd.DataFrame:
    """Estado de resultados por ano, para revisar el modelo a mano."""
    years = inputs.project_years
    utilization = _ramp(inputs.utilization_ramp, years)
    wc_ratio = (
        inputs.wc_inventory_days + inputs.wc_receivable_days - inputs.wc_payable_days
    ) / 365.0

    rows = []
    for index in range(years):
        volume = inputs.capacity_kg_year * utilization[index]
        learning = _learning_factor(inputs.learning_rate, index)
        revenue = volume * inputs.fob_price_usd_per_kg
        variable_costs = volume * (inputs.purchase_cost_usd_per_kg + inputs.variable_cost_usd_per_kg) * learning
        commission = revenue * inputs.sales_commission
        compliance = revenue * inputs.compliance_pct_fct
        depreciation = (
            inputs.capex_usd / inputs.depreciation_years if index < inputs.depreciation_years else 0.0
        )
        ebit = revenue - variable_costs - inputs.opex_fixed_usd_year - commission - compliance - depreciation
        taxes = max(0.0, ebit) * inputs.tax_rate
        rows.append(
            {
                "year": index + 1,
                "utilization": utilization[index],
                "volume_kg": round(volume, 1),
                "revenue_usd": round(revenue, 2),
                "variable_costs_usd": round(variable_costs, 2),
                "opex_fixed_usd": round(inputs.opex_fixed_usd_year, 2),
                "commission_usd": round(commission, 2),
                "compliance_usd": round(compliance, 2),
                "depreciation_usd": round(depreciation, 2),
                "ebit_usd": round(ebit, 2),
                "ebit_margin": round(ebit / revenue, 4) if revenue else None,
                "taxes_usd": round(taxes, 2),
                "net_income_usd": round(ebit - taxes, 2),
                "working_capital_usd": round(volume * inputs.fob_price_usd_per_kg * wc_ratio, 2),
            }
        )
    return pd.DataFrame(rows)
