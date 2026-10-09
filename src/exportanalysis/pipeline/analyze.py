"""Analisis completo de un producto: data publica -> indicadores -> inversion.

Este es el modulo que la API web y los scripts usan. Devuelve un dict plano
listo para serializar a JSON y pintar en el frontend.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from ..config import get_product, load_assumptions, load_catalog
from ..model.financials import ProjectInputs, annual_pnl, build_cashflows
from ..model.unit_economics import analyze_unit_economics
from ..model.valuation import breakeven, run_sensitivity, summarize
from ..pipeline import competitors, market
from ..sources import comtrade, manual_tariffs
from . import pricing
from .landed_cost import landed_cost, price_positioning

log = logging.getLogger(__name__)


def _top_destinations(trade: pd.DataFrame) -> list[int]:
    frame = market.destination_breakdown(trade)
    if frame.empty:
        return []
    return frame["partner_code"].head(6).tolist()


def _resolve_ramp(
    implied: dict, configured: list[float], capacity_kg: float, fob_price: float
) -> tuple[list[float], dict]:
    """Decide la curva de ocupacion: la que pide el mercado o la del config.

    Preferencia por la data, con el config como respaldo declarado. Se reporta
    siempre cual se uso y por que: un ramp sin origen conocido es un supuesto
    invisible, que es la peor forma de supuesto.
    """
    years = 5
    fallback = {
        "source": "config",
        "reason": "El analisis de mercado no pudo derivar un volumen, se uso utilization_ramp del config.",
    }

    if not implied.get("available") or not implied.get("implied_volume_kg"):
        return configured, fallback

    # El ramp nunca excede la capacidad instalada.
    target_kg = min(implied["implied_volume_kg"], capacity_kg)
    peak = target_kg / capacity_kg if capacity_kg else 0.0
    if peak <= 0:
        return configured, {**fallback, "reason": "El mercado no sugiere volumen positivo."}

    # Curva de arranque: suave al inicio, plana al final. La forma exacta es una
    # decision; lo que importa es que este escrita y sea revisable.
    shape = [0.45, 0.75, 0.92, 1.0, 1.0]
    ramp = [round(peak * s, 4) for s in shape[:years]]

    return ramp, {
        "source": "mercado",
        "reason": (
            f"El headroom de mercado a la participacion objetivo implica "
            f"{implied['implied_volume_kg']:,.0f} kg/ano, equivalente a {peak * 100:.0f}% "
            f"de la capacidad instalada. Cuello de botella: {implied.get('binds')}."
        ),
        "implied_volume_kg": implied["implied_volume_kg"],
        "binds": implied.get("binds"),
        "fob_price_used": fob_price,
    }


def _real_tariff(hs6: str, destinations: list[int]) -> float | None:
    """Arancel mas reciente disponible entre los destinos principales."""
    for code in destinations:
        value = manual_tariffs.tariff_for(hs6, code)
        if value is not None:
            return value
    return None


def _records(frame: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts con null en vez de NaN.

    Un DataFrame de comercio tiene huecos legitimos: un pais que no reporto
    ese anio, un precio unitario que no se puede calcular sin volumen. Esos
    huecos son `NaN` en pandas, y `NaN` no es JSON valido, asi que la
    serializacion falla con un error poco descriptivo. Convertirlos a `None`
    en el borde deja que el frontend muestre "n/d".
    """
    if frame is None or frame.empty:
        return []
    return frame.where(pd.notna(frame), None).to_dict("records")


def analyze_product(slug: str, *, target_share: float | None = None) -> dict[str, Any]:
    """Analisis completo de un producto del catalogo.

    target_share: participacion de mercado objetivo. Si es None se deriva como
    "share actual + 2 puntos porcentuales" (ver competitors.default_target_share),
    que es la unica forma de que la pregunta tenga sentido para cualquier producto.
    """
    product = get_product(slug)
    catalog = load_catalog()
    reporter = catalog.defaults.reporter
    model_defaults = load_assumptions().defaults
    years = comtrade.year_window(model_defaults.project_years)

    log.info("Analizando %s (%s)", product.name, product.hs6)

    trade = comtrade.fetch_trade(
        product.hs6,
        reporter=reporter,
        flow=catalog.defaults.flow,
        years=years,
    )
    market_summary = market.market_summary(trade)
    if not market_summary.get("available"):
        return {
            "slug": slug,
            "product": product.model_dump(),
            "market": market_summary,
            "error": market_summary.get("message"),
        }

    comp = competitors.share_trends(product.hs6, reporter, product.competitors)

    # Precio de referencia: el unit value del ultimo anio con data.
    price = market_summary.get("latest_unit_value_usd")
    fob_price = price if price else 0.0
    price_calc = pricing.estimated_fob_price_usd_per_kg(product.hs6)
    fob_price_calc = price_calc.get("price_usd_per_kg") if price_calc.get("price_usd_per_kg") is not None else fob_price
    capex_inputs = load_assumptions().for_product(slug)
    capacity = capex_inputs["capacity_kg_year"]

    # --- Cerrar el circuito: cuanto permite el mercado, no un ramp inventado ---
    if target_share is None:
        target_share = competitors.default_target_share(product.hs6, reporter, product.competitors)

    room = competitors.headroom_ladder(
        product.hs6, reporter, product.competitors, unit_value_usd_per_kg=fob_price or None
    )
    implied = competitors.implied_capacity_usd(
        product.hs6, reporter, product.competitors, target_share, capacity,
        fob_price or None,
    )
    ramp, ramp_source = _resolve_ramp(implied, model_defaults.utilization_ramp, capacity, fob_price)

    assumed = ProjectInputs(
        slug=slug,
        capacity_kg_year=capacity,
        capex_usd=capex_inputs["capex_usd"],
        variable_cost_usd_per_kg=capex_inputs["variable_cost_usd_per_kg"],
        purchase_cost_usd_per_kg=capex_inputs["purchase_cost_usd_per_kg"],
        opex_fixed_usd_year=capex_inputs["opex_fixed_usd_year"],
        working_capital_usd=capex_inputs["working_capital_usd"],
        project_years=model_defaults.project_years,
        discount_rate=model_defaults.discount_rate,
        tax_rate=model_defaults.tax_rate,
        learning_rate=model_defaults.learning_rate,
        sales_commission=model_defaults.sales_commission,
        freight_pct_fob=model_defaults.freight_pct_fob,
        compliance_pct_fct=model_defaults.compliance_pct_fob,
        wc_inventory_days=model_defaults.wc_inventory_days,
        wc_receivable_days=model_defaults.wc_receivable_days,
        wc_payable_days=model_defaults.wc_payable_days,
        depreciation_years=model_defaults.depreciation_years,
        capex_schedule=model_defaults.capex_schedule,
        utilization_ramp=ramp,
        fob_price_usd_per_kg=fob_price,
        capture_share=target_share,
    )

    outputs = build_cashflows(assumed)
    pnl = annual_pnl(assumed)

    # Chequeo de economia unitaria ANTES de mirar el VAN. Si el margen por kilo
    # es negativo, el VAN negativo es consecuencia y no informacion.
    unit = analyze_unit_economics(
        fob_price,
        purchase_cost_usd_per_kg=capex_inputs["purchase_cost_usd_per_kg"],
        variable_cost_usd_per_kg=capex_inputs["variable_cost_usd_per_kg"],
        sales_commission=model_defaults.sales_commission,
        compliance_pct_fob=model_defaults.compliance_pct_fob,
        freight_pct_fob=model_defaults.freight_pct_fob,
    )

    # Aranceles de los mercados destino realmente relevantes para este producto.
    destinations = _top_destinations(trade)
    tariffs = (
        manual_tariffs.tariff_table(product.hs6, destinations) if destinations else pd.DataFrame()
    )
    real_tariff = _real_tariff(product.hs6, destinations)
    landed = (
        landed_cost(fob_price, freight_pct_fob=model_defaults.freight_pct_fob, duty_pct=real_tariff)
        if fob_price
        else {}
    )
    positioning = (
        price_positioning(
            fob_price, freight_pct_fob=model_defaults.freight_pct_fob, duty_pct=real_tariff
        )
        if fob_price
        else {}
    )

    return {
        "slug": slug,
        "product": product.model_dump(),
        "years": years,
        "market": market_summary,
        "destinations": _records(market.destination_breakdown(trade)),
        "competitors": comp,
        "headroom": room,
        "implied_volume": implied,
        "unit_economics": unit,
        "tariffs": _records(tariffs),
        "landed_cost": landed,
        "price_positioning": positioning,
        "pricing": price_calc,
        "investment": {
            "inputs": assumed.__dict__,
            "ramp_source": ramp_source,
            "summary": summarize(outputs, assumed),
            "pnl": _records(pnl),
            "cashflows": outputs.cashflows,
            "sensitivity": run_sensitivity(assumed, load_assumptions().sensitivity),
            "breakeven": breakeven(assumed),
        },
        "data_quality": {
            "market_data_source": "UN Comtrade (API publica)",
            "years_with_data": sorted(trade["year"].dropna().unique().tolist()),
            "tariff_source": "data/raw/tariffs/tariffs.csv (carga manual)",
            "assumptions_source": "config/assumptions.yaml (supuestos, no data)",
            "warning": (
                "El arancel es un supuesto cargado a mano. Si duty_pct esta vacio, "
                "el modelo usa 0% y eso subestima el costo en destino."
            ),
        },
    }

