"""Analisis completo de un producto: data publica -> indicadores -> inversion.

Este es el modulo que la API web y los scripts usan. Devuelve un dict plano
listo para serializar a JSON y pintar en el frontend.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

import pandas as pd

from ..config import get_product, load_assumptions, load_catalog
from ..model.financials import (
    ProjectInputs,
    annual_pnl,
    build_cashflows,
)
from ..model.unit_economics import analyze_unit_economics
from ..model.valuation import breakeven, run_monte_carlo, run_sensitivity, summarize
from ..pipeline import competitors, market
from ..sources import manual_tariffs
from . import excel_analysis, pricing
from .landed_cost import landed_cost, price_positioning

log = logging.getLogger(__name__)


def _top_destinations(trade: pd.DataFrame) -> list[int]:
    frame = market.destination_breakdown(trade)
    if frame.empty:
        return []
    return frame["partner_code"].head(6).tolist()


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


def _sunat_block(nandina: str | None) -> dict:
    """Precio promedio por kilo desde el Excel SUNAT (FOB / peso neto), por anio.

    Solo existe para los productos que tienen cargado su Excel de SUNAT con una
    hoja por anio. Cuando esta, es la fuente de precio mas confiable: trae el
    peso neto real de cada operacion y no depende de la unidad del snapshot.
    """
    if not nandina:
        return {"available": False}
    try:
        summary = excel_analysis.sunat_annual_summary(nandina)
    except (FileNotFoundError, KeyError, ValueError):
        return {"available": False}
    if summary.empty:
        return {"available": False}

    valid = summary.dropna(subset=["price_usd_per_kg"])
    latest = valid.iloc[-1] if not valid.empty else None
    return {
        "available": True,
        "nandina": nandina,
        "series": _records(summary),
        "latest_year": int(latest["year"]) if latest is not None else None,
        "latest_price_usd_per_kg": (
            float(latest["price_usd_per_kg"]) if latest is not None else None
        ),
        "cagr_price": market.cagr(summary["price_usd_per_kg"]),
    }


def _compute_projection(
    series: list[dict],
    *,
    value_key: str = "fob_usd",
    method: str = "moving_average",
    window: int = 3,
    forecast_years: int = 2,
    degree: int = 2,
) -> dict:
    """Selecciona y ejecuta el metodo de proyeccion solicitado.

    Metodos disponibles:
      - moving_average: media movil simple (default, window=3)
      - linear: tendencia lineal (grado 1)
      - quadratic: tendencia cuadratica (grado 2)
      - cagr: proyeccion por CAGR historico (ultimos 5 anos)
    """
    if method == "linear":
        result = market.trend_projection(
            series, value_key=value_key, degree=1, forecast_years=forecast_years
        )
        if result.get("available"):
            result["method"] = "linear"
        return result
    if method == "quadratic":
        result = market.trend_projection(
            series, value_key=value_key, degree=degree, forecast_years=forecast_years
        )
        if result.get("available"):
            result["method"] = "quadratic"
        return result
    if method == "cagr":
        result = _cagr_projection(series, value_key=value_key, forecast_years=forecast_years)
        if result.get("available"):
            result["method"] = "cagr"
        return result
    # default: moving_average
    result = market.moving_average_projection(
        series, value_key=value_key, window=window, forecast_years=forecast_years
    )
    if result.get("available"):
        result["method"] = "moving_average"
    return result


def _cagr_projection(
    series: list[dict],
    *,
    value_key: str = "fob_usd",
    forecast_years: int = 2,
    lookback_years: int = 5,
) -> dict:
    """Proyecta usando el CAGR de los ultimos N anos."""
    import numpy as np

    pts = [
        (int(r["year"]), float(r[value_key]))
        for r in series
        if r.get("year") is not None and r.get(value_key) is not None and np.isfinite(float(r[value_key]))
    ]
    pts = [(y, v) for y, v in pts if v > 0]
    if len(pts) < 2:
        return {
            "available": False,
            "message": "Hacen falta al menos 2 años con valor positivo para calcular CAGR.",
        }

    # Tomar los ultimos lookback_years
    pts = sorted(pts)[-lookback_years:]
    first_year, first_val = pts[0]
    last_year, last_val = pts[-1]
    periods = last_year - first_year
    if periods <= 0 or first_val <= 0 or last_val <= 0:
        return {
            "available": False,
            "message": "No se puede calcular CAGR con los datos disponibles.",
        }

    cagr = (last_val / first_val) ** (1 / periods) - 1

    historical = [{"year": y, "value": v} for y, v in pts]
    last_year_total = pts[-1][0]
    last_val_total = pts[-1][1]
    forecast = [
        {"year": last_year_total + i, "value": last_val_total * (1 + cagr) ** i}
        for i in range(1, forecast_years + 1)
    ]
    forecast_years_list = [f["year"] for f in forecast]

    return {
        "available": True,
        "method": f"CAGR {periods} años ({cagr*100:.1f}%)",
        "cagr_pct": round(cagr * 100, 1),
        "forecast_years": forecast_years_list,
        "historical": historical,
        "forecast": forecast,
        "average_value": last_val_total,
    }


def _analyze_product_uncached(
    slug: str,
    *,
    target_share: float | None = None,
    price_usd_per_kg: float | None = None,
    capacity_kg_year: float | None = None,
    year1_volume_kg: float | None = None,
    annual_volume_growth_pct: float | None = None,
    purchase_cost_usd_per_kg: float | None = None,
    variable_cost_usd_per_kg: float | None = None,
    capex_usd: float | None = None,
    opex_fixed_usd_year: float | None = None,
    working_capital_usd: float | None = None,
    discount_rate: float | None = None,
    price_volatility_pct: float | None = None,
    purchase_cost_volatility_pct: float | None = None,
    volume_volatility_pct: float | None = None,
    projection_method: str = "moving_average",
) -> dict[str, Any]:
    """Analisis de mercado y, si hay datos, evaluacion financiera ingresada por el usuario.

    target_share: participacion de mercado objetivo. Si es None se deriva como
    "share actual + 2 puntos porcentuales" (ver competitors.default_target_share).

    price_usd_per_kg: precio FOB de venta en USD/kg.

    Los argumentos financieros opcionales se solicitan al usuario; sin todos
    ellos se conserva el analisis de mercado pero no se calcula una valuacion.
    """
    product = get_product(slug)
    catalog = load_catalog()
    reporter = catalog.defaults.reporter
    model_defaults = load_assumptions().defaults

    log.info("Analizando %s (%s)", product.name, product.hs6)

    # Datos 100% locales: Trade Map en Excel. La ventana de anos sale de los
    # anios que realmente trae el archivo, no de una funcion que asuma red.
    trade = excel_analysis.peru_exports_trade(product.hs6, product.nandina)
    years = sorted(trade["year"].dropna().astype(int).unique().tolist())
    try:
        import_demand = market.import_demand_summary(
            excel_analysis.world_imports(product.hs6),
            excel_analysis.world_import_quantities(product.hs6),
        )
    except FileNotFoundError:
        import_demand = {"available": False, "destinations": []}

    market_summary = market.market_summary(trade)
    if not market_summary.get("available"):
        return {
            "slug": slug,
            "product": product.model_dump(),
            "market": market_summary,
            "import_demand": import_demand,
            "error": market_summary.get("message"),
        }

    comp = competitors.share_trends(product.hs6, reporter, product.competitors)

    # Participacion de mercado mundial por pais exportador, ano por ano: alimenta
    # el grafico circular con filtro de fecha. Top N + resto + Peru destacado.
    share_by_year = competitors.world_share_by_year(product.hs6, reporter, top_n=9)

    # Proyecta el valor FOB peruano con el metodo seleccionado.
    projection = _compute_projection(
        market_summary.get("series") or [],
        value_key="fob_usd",
        method=projection_method,
        forecast_years=2,
    )

    # Precio de venta: input editable. Orden de resolucion:
    #   1. lo que paso el usuario
    #   2. SUNAT (FOB / peso neto), si el producto tiene su Excel cargado
    #   3. estimado de los historicos (pricing, snapshot Trade Map)
    #   4. unit value del Excel como ultimo respaldo
    price_calc = pricing.estimated_fob_price_usd_per_kg(product.hs6)
    sunat_calc = pricing.sunat_fob_price_usd_per_kg(product.nandina)
    if price_usd_per_kg is not None:
        fob_price = float(price_usd_per_kg)
        price_origin = pricing.PRICE_ORIGIN_USER
    elif sunat_calc.get("price_usd_per_kg") is not None:
        fob_price = float(sunat_calc["price_usd_per_kg"])
        price_origin = pricing.PRICE_ORIGIN_SUNAT
    elif price_calc.get("price_usd_per_kg") is not None:
        fob_price = float(price_calc["price_usd_per_kg"])
        price_origin = pricing.PRICE_ORIGIN_CALCULATED
    else:
        excel_price = market_summary.get("latest_unit_value_usd")
        fob_price = float(excel_price) if excel_price else 0.0
        price_origin = pricing.PRICE_ORIGIN_EXCEL
    price_calc = {
        **price_calc,
        "price_usd_per_kg": fob_price,
        "origin": price_origin,
        "sunat": sunat_calc,
    }

    sunat_block = _sunat_block(product.nandina)

    # Aranceles y costo puesto en destino: no dependen de los supuestos, asi que
    # se calculan una vez y sirven tanto al analisis completo como al parcial.
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

    room = competitors.headroom_ladder(
        product.hs6, reporter, product.competitors, unit_value_usd_per_kg=fob_price or None
    )

    # Sin supuestos no hay modelo de inversion, pero el analisis de mercado si es
    # real: se entrega completo y se marca explicitamente lo que falta, en vez de
    # fallar. Es el caso normal de un producto recien agregado por su carpeta.
    assumptions = load_assumptions()
    overrides = {
        "capacity_kg_year": capacity_kg_year,
        "year1_volume_kg": year1_volume_kg,
        "annual_volume_growth_pct": annual_volume_growth_pct,
        "capex_usd": capex_usd,
        "variable_cost_usd_per_kg": variable_cost_usd_per_kg,
        # The UI's single variable-cost input covers raw material and processing.
        "purchase_cost_usd_per_kg": purchase_cost_usd_per_kg if purchase_cost_usd_per_kg is not None else 0.0,
        "opex_fixed_usd_year": opex_fixed_usd_year,
        "working_capital_usd": working_capital_usd or 0.0,
        "discount_rate": discount_rate,
    }
    if capacity_kg_year is None and year1_volume_kg is not None and annual_volume_growth_pct is not None:
        projected_volumes = [
            year1_volume_kg * (1 + annual_volume_growth_pct / 100) ** year
            for year in range(model_defaults.project_years)
        ]
        overrides["capacity_kg_year"] = max(projected_volumes)
    elif capacity_kg_year is None:
        overrides["capacity_kg_year"] = 0.0
    missing = assumptions.missing_for(slug, overrides)
    if year1_volume_kg is None:
        missing.append("year1_volume_kg")
    if annual_volume_growth_pct is None:
        missing.append("annual_volume_growth_pct")
    if fob_price <= 0:
        missing.append("price_usd_per_kg")
    missing = list(dict.fromkeys(missing))
    if missing:
        return {
            "slug": slug,
            "product": product.model_dump(),
            "years": years,
            "market": market_summary,
            "import_demand": import_demand,
            "sunat": sunat_block,
            "destinations": _records(market.destination_breakdown(trade)),
            "competitors": comp,
            "share_by_year": share_by_year,
            "projection": projection,
            "headroom": room,
            "implied_volume": {
                "available": False,
                "message": "Faltan supuestos de capacidad para traducir el espacio de mercado a volumen.",
            },
            "unit_economics": None,
            "tariffs": _records(tariffs),
            "landed_cost": landed,
            "price_positioning": positioning,
            "pricing": price_calc,
            "investment": None,
            "assumptions_missing": missing,
            "data_quality": {
                "market_data_source": "Trade Map (Excel local)",
                "price_source": price_origin,
                "sunat_source": (
                    f"Excel SUNAT {product.nandina} (FOB y peso neto por año)"
                    if sunat_block.get("available")
                    else "no disponible para este producto"
                ),
                "years_with_data": years,
                "tariff_source": "data/raw/tariffs/tariffs.csv (carga manual)",
                "assumptions_source": "config/assumptions.yaml (supuestos, no data)",
                "warning": (
                    "Faltan supuestos de inversion para este producto. El análisis de "
                    "mercado de arriba es real; completa los campos del formulario "
                    "para habilitar el modelo."
                ),
            },
        }

    capex_inputs = assumptions.for_product(slug, overrides)
    capacity = capex_inputs["capacity_kg_year"]
    year1_volume = year1_volume_kg if year1_volume_kg is not None else capex_inputs["year1_volume_kg"]
    annual_growth = annual_volume_growth_pct if annual_volume_growth_pct is not None else capex_inputs["annual_volume_growth_pct"]
    if capacity <= 0:
        raise ValueError("La capacidad anual debe ser mayor que cero.")
    if year1_volume <= 0 or year1_volume > capacity:
        raise ValueError("El volumen del primer año debe ser mayor que cero y no superar la capacidad.")
    if annual_growth < -100:
        raise ValueError("El crecimiento anual no puede ser inferior a -100%.")

    # Overrides interactivos del usuario (o defaults del catalogo)
    eff_purchase_cost = float(capex_inputs["purchase_cost_usd_per_kg"])
    eff_variable_cost = float(capex_inputs["variable_cost_usd_per_kg"])
    eff_capex = float(capex_inputs["capex_usd"])
    eff_discount_rate = float(capex_inputs["discount_rate"])

    # --- Cerrar el circuito: cuanto permite el mercado, no un ramp inventado ---
    if target_share is None:
        target_share = competitors.default_target_share(product.hs6, reporter, product.competitors)

    implied = competitors.implied_capacity_usd(
        product.hs6, reporter, product.competitors, target_share, capacity,
        fob_price or None,
    )
    ramp = [
        min(1.0, year1_volume * (1 + annual_growth / 100) ** year / capacity)
        for year in range(model_defaults.project_years)
    ]
    ramp_source = {
        "source": "usuario",
        "reason": "Volumen inicial y crecimiento anual ingresados en el formulario.",
    }

    base_project = ProjectInputs(
        slug=slug,
        capacity_kg_year=capacity,
        capex_usd=eff_capex,
        variable_cost_usd_per_kg=eff_variable_cost,
        purchase_cost_usd_per_kg=eff_purchase_cost,
        opex_fixed_usd_year=capex_inputs["opex_fixed_usd_year"],
        working_capital_usd=capex_inputs["working_capital_usd"],
        year1_volume_kg=year1_volume,
        annual_volume_growth_pct=annual_growth,
        project_years=model_defaults.project_years,
        discount_rate=eff_discount_rate,
        tax_rate=model_defaults.tax_rate,
        learning_rate=model_defaults.learning_rate,
        sales_commission=model_defaults.sales_commission,
        freight_pct_fob=model_defaults.freight_pct_fob,
        compliance_pct_fct=model_defaults.compliance_pct_fob,
        depreciation_years=model_defaults.depreciation_years,
        capex_schedule=model_defaults.capex_schedule,
        utilization_ramp=ramp,
        fob_price_usd_per_kg=fob_price,
        capture_share=target_share,
    )

    assumed = base_project

    outputs = build_cashflows(assumed)
    pnl = annual_pnl(assumed)

    # Chequeo de economia unitaria ANTES de mirar el VAN. Si el margen por kilo
    # es negativo, el VAN negativo es consecuencia y no informacion.
    unit = analyze_unit_economics(
        fob_price,
        purchase_cost_usd_per_kg=assumed.purchase_cost_usd_per_kg,
        variable_cost_usd_per_kg=assumed.variable_cost_usd_per_kg,
        sales_commission=model_defaults.sales_commission,
        compliance_pct_fob=model_defaults.compliance_pct_fob,
        freight_pct_fob=model_defaults.freight_pct_fob,
    )

    monte_carlo_missing = [
        name
        for name, value in (
            ("price_volatility_pct", price_volatility_pct),
            ("variable_cost_volatility_pct", purchase_cost_volatility_pct),
            ("volume_volatility_pct", volume_volatility_pct),
        )
        if value is None
    ]
    monte_carlo = None
    if not monte_carlo_missing:
        assert price_volatility_pct is not None
        assert purchase_cost_volatility_pct is not None
        assert volume_volatility_pct is not None
        monte_carlo = run_monte_carlo(
            assumed,
            price_volatility=price_volatility_pct / 100,
            variable_cost_volatility=purchase_cost_volatility_pct / 100,
            volume_volatility=volume_volatility_pct / 100,
        )

    return {
        "slug": slug,
        "product": product.model_dump(),
        "years": years,
        "market": market_summary,
        "import_demand": import_demand,
        "sunat": sunat_block,
        "destinations": _records(market.destination_breakdown(trade)),
        "competitors": comp,
        "share_by_year": share_by_year,
        "projection": projection,
        "headroom": room,
        "implied_volume": implied,
        "unit_economics": unit,
        "tariffs": _records(tariffs),
        "landed_cost": landed,
        "price_positioning": positioning,
        "pricing": price_calc,
        "assumptions_missing": [],
        "investment": {
            "inputs": assumed.__dict__,
            "ramp_source": ramp_source,
            "summary": summarize(outputs, assumed),
            "pnl": _records(pnl),
            "cashflows": outputs.cashflows,
            "sensitivity": run_sensitivity(assumed, load_assumptions().sensitivity),
            "breakeven": breakeven(assumed),
            "monte_carlo": monte_carlo,
            "monte_carlo_missing": monte_carlo_missing,
        },
        "data_quality": {
            "market_data_source": "Trade Map (Excel local)",
            "price_source": price_origin,
            "sunat_source": (
                f"Excel SUNAT {product.nandina} (FOB y peso neto por año)"
                if sunat_block.get("available")
                else "no disponible para este producto"
            ),
            "years_with_data": years,
            "tariff_source": "data/raw/tariffs/tariffs.csv (carga manual)",
            "assumptions_source": "config/assumptions.yaml (supuestos, no data)",
            "warning": (
                "El arancel es un supuesto cargado a mano. Si duty_pct está vacío, "
                "el modelo usa 0% y eso subestima el costo en destino."
            ),
        },
    }


@functools.lru_cache(maxsize=256)
def _analyze_cached(
    token: tuple,
    slug: str,
    target_share: float | None,
    price_usd_per_kg: float | None,
    capacity_kg_year: float | None,
    year1_volume_kg: float | None,
    annual_volume_growth_pct: float | None,
    purchase_cost_usd_per_kg: float | None,
    variable_cost_usd_per_kg: float | None,
    capex_usd: float | None,
    opex_fixed_usd_year: float | None,
    working_capital_usd: float | None,
    discount_rate: float | None,
    price_volatility_pct: float | None,
    purchase_cost_volatility_pct: float | None,
    volume_volatility_pct: float | None,
    projection_method: str,
) -> dict[str, Any]:
    return _analyze_product_uncached(
        slug,
        target_share=target_share,
        price_usd_per_kg=price_usd_per_kg,
        capacity_kg_year=capacity_kg_year,
        year1_volume_kg=year1_volume_kg,
        annual_volume_growth_pct=annual_volume_growth_pct,
        purchase_cost_usd_per_kg=purchase_cost_usd_per_kg,
        variable_cost_usd_per_kg=variable_cost_usd_per_kg,
        capex_usd=capex_usd,
        opex_fixed_usd_year=opex_fixed_usd_year,
        working_capital_usd=working_capital_usd,
        discount_rate=discount_rate,
        price_volatility_pct=price_volatility_pct,
        purchase_cost_volatility_pct=purchase_cost_volatility_pct,
        volume_volatility_pct=volume_volatility_pct,
        projection_method=projection_method,
    )


def analyze_product(
    slug: str,
    *,
    target_share: float | None = None,
    price_usd_per_kg: float | None = None,
    capacity_kg_year: float | None = None,
    year1_volume_kg: float | None = None,
    annual_volume_growth_pct: float | None = None,
    purchase_cost_usd_per_kg: float | None = None,
    variable_cost_usd_per_kg: float | None = None,
    capex_usd: float | None = None,
    opex_fixed_usd_year: float | None = None,
    working_capital_usd: float | None = None,
    discount_rate: float | None = None,
    price_volatility_pct: float | None = None,
    purchase_cost_volatility_pct: float | None = None,
    volume_volatility_pct: float | None = None,
    projection_method: str = "moving_average",
) -> dict[str, Any]:
    """Fachada memoizada de analyze_product.

    Un analisis completo lee media docena de Excel y recalcula escenarios
    (tornado de sensibilidad). En la web eso se pagaba en cada request
    simulador, aunque los Excel en data/ no hubieran cambiado. Se memoriza por
    (slug, supuestos, huella de los Excel). La huella (data_token) lleva el
    mtime de cada archivo: si alguien reemplaza un Excel, la huella cambia y el
    resultado se recalcula solo, sin reiniciar el proceso.

    Contrato: el dict devuelto se COMPARTE entre llamadas con la misma clave.
    Quien lo reciba no debe mutarlo. Los consumidores actuales (endpoints de la
    API, dossier, screener) solo leen o copian via _json_safe, asi que es seguro.
    maxsize acota la memoria: con el simulador cada combinacion de supuestos es
    una entrada distinta.
    """
    product = get_product(slug)
    token = excel_analysis.data_token(product.hs6, product.nandina)
    return _analyze_cached(
        token,
        slug,
        target_share,
        price_usd_per_kg,
        capacity_kg_year,
        year1_volume_kg,
        annual_volume_growth_pct,
        purchase_cost_usd_per_kg,
        variable_cost_usd_per_kg,
        capex_usd,
        opex_fixed_usd_year,
        working_capital_usd,
        discount_rate,
        price_volatility_pct,
        purchase_cost_volatility_pct,
        volume_volatility_pct,
        projection_method,
    )
