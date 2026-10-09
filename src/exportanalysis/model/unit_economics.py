"""Economia unitaria: el chequeo que hay que hacer ANTES del modelo.

Por que existe
==============
Un modelo de inversion con supuestos mal puestos produce un VAN negativo
perfectamente explicable, y ahi esta el peligro: uno se convence de que "el
negocio no da" cuando en realidad lo que esta mal es el precio de compra que
se escribio a ojo. Peor todavia es al reves: un VAN positivo por un supuesto de
precio de compra equivocado.

Este modulo separa las tres cosas que se confunden constantemente:
    1. Lo que dice la data publicada (precio FOB unitario real del producto).
    2. Lo que TU operacion cuesta (compra + procesamiento + fijos).
    3. Lo que queda entre ambos (margen bruto por kilo).

Si (3) es negativo, el resto del modelo no importa. Se dice aqui, primero.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UnitEconomics:
    fob_price_usd_per_kg: float
    purchase_cost_usd_per_kg: float
    processing_cost_usd_per_kg: float
    commission_usd_per_kg: float
    compliance_usd_per_kg: float
    freight_usd_per_kg: float

    @property
    def total_variable_cost(self) -> float:
        return (
            self.purchase_cost_usd_per_kg
            + self.processing_cost_usd_per_kg
            + self.commission_usd_per_kg
            + self.compliance_usd_per_kg
        )

    @property
    def gross_margin_usd_per_kg(self) -> float:
        """Lo que queda al exportador por kilo, antes de opex fijo y depreciacion."""
        return self.fob_price_usd_per_kg - self.total_variable_cost

    @property
    def gross_margin_pct(self) -> float:
        return self.gross_margin_usd_per_kg / self.fob_price_usd_per_kg

    @property
    def is_viable(self) -> bool:
        return self.gross_margin_usd_per_kg > 0

    def breakeven_price(self) -> float:
        """Precio FOB minimo para no perder dinero en cada kilo."""
        return self.total_variable_cost

    def to_dict(self) -> dict:
        return {
            "fob_price_usd_per_kg": round(self.fob_price_usd_per_kg, 4),
            "purchase_cost_usd_per_kg": round(self.purchase_cost_usd_per_kg, 4),
            "processing_cost_usd_per_kg": round(self.processing_cost_usd_per_kg, 4),
            "commission_usd_per_kg": round(self.commission_usd_per_kg, 4),
            "compliance_usd_per_kg": round(self.compliance_usd_per_kg, 4),
            "total_variable_cost_usd_per_kg": round(self.total_variable_cost, 4),
            "gross_margin_usd_per_kg": round(self.gross_margin_usd_per_kg, 4),
            "gross_margin_pct": round(self.gross_margin_pct, 4),
            "freight_usd_per_kg": round(self.freight_usd_per_kg, 4),
            "breakeven_fob_price_usd_per_kg": round(self.breakeven_price(), 4),
            "is_viable": self.is_viable,
        }


def analyze_unit_economics(
    fob_price_usd_per_kg: float,
    *,
    purchase_cost_usd_per_kg: float,
    variable_cost_usd_per_kg: float,
    sales_commission: float,
    compliance_pct_fob: float,
    freight_pct_fob: float,
) -> dict:
    """Diagnostico completo, con las advertencias que aplican."""
    unit = UnitEconomics(
        fob_price_usd_per_kg=fob_price_usd_per_kg,
        purchase_cost_usd_per_kg=purchase_cost_usd_per_kg,
        processing_cost_usd_per_kg=variable_cost_usd_per_kg,
        commission_usd_per_kg=fob_price_usd_per_kg * sales_commission,
        compliance_usd_per_kg=fob_price_usd_per_kg * compliance_pct_fob,
        freight_usd_per_kg=fob_price_usd_per_kg * freight_pct_fob,
    )
    result = unit.to_dict()

    warnings: list[str] = []
    if not unit.is_viable:
        warnings.append(
            f"MARGEN NEGATIVO: se paga USD {unit.total_variable_cost:.2f}/kg en costos "
            f"variables y el FOB del mercado es USD {fob_price_usd_per_kg:.2f}/kg. "
            f"Faltan USD {abs(unit.gross_margin_usd_per_kg):.2f}/kg. Con estos supuestos "
            "el proyecto pierde dinero en CADA kilo vendido, antes de pagar planilla. "
            "Revisar precio de compra y costo de procesamiento contra cotizaciones reales; "
            "el resto del modelo no es concluyente hasta entonces."
        )
    elif unit.gross_margin_pct < 0.10:
        warnings.append(
            f"Margen ajustado ({unit.gross_margin_pct * 100:.1f}%): cualquier desviacion "
            "de volumen o costo deja el proyecto sin utilidad. Exige mucho control de costos."
        )

    result["warnings"] = warnings
    result["headline"] = (
        f"Margen bruto USD {unit.gross_margin_usd_per_kg:.2f}/kg "
        f"({unit.gross_margin_pct * 100:.1f}%)"
    )
    return result
