"""Screener: ranking de productos para decidir por cual empezar.

La ficha individual responde "¿como le va a este producto?". Este modulo
responde la otra pregunta, la que uno se hace antes: "de todo el catalogo,
¿cual miro primero?".

Corre el MISMO pipeline que la ficha (analyze_product) para cada producto y
arma una tabla comparable: normaliza cada metrica a 0-100 entre los productos,
la pondera con los pesos de config/scoring.yaml y produce un puntaje. Todo
offline, desde los Excel locales.

Honestidad por diseno
=====================
Un ranking es peligroso si esconde de donde sale cada numero. Por eso:

  - Cada metrica declara su `basis` (dato publicado / supuesto / mixto).
  - Cada producto trae `readiness`: que archivos tiene y si sus supuestos
    siguen siendo de ejemplo (`assumptions_verified`).
  - El puntaje se calcula SOLO sobre las metricas disponibles del producto, y
    se publica `score_confidence` para que un producto con pocos datos no
    aparente ser mejor de lo que la evidencia sostiene.

Este screener no recomienda invertir. Ordena la conversacion.
"""

from __future__ import annotations

import functools

from ..config import get_product, load_assumptions, load_catalog, load_scoring
from ..sources import manual_tariffs
from . import excel_analysis
from .analyze import analyze_product

# Especificacion por defecto de cada dimension. config/scoring.yaml la
# sobrescribe (label, peso, direccion). Si el YAML falta, el screener corre
# igual: la app no depende de un archivo opcional para funcionar.
DEFAULT_METRICS: dict[str, dict] = {
    "market_size": {
        "label": "Tamaño de mercado",
        "weight": 0.8,
        "lower_is_better": False,
        "basis": "dato publicado",
        "description": "Exportaciones FOB de Perú del último año con data.",
    },
    "growth": {
        "label": "Crecimiento",
        "weight": 1.0,
        "lower_is_better": False,
        "basis": "dato publicado",
        "description": "CAGR del valor FOB en la ventana analizada.",
    },
    "concentration": {
        "label": "Diversidad de destinos",
        "weight": 1.0,
        "lower_is_better": True,
        "basis": "dato publicado",
        "description": "Menor concentración top 5 destinos = menor riesgo comercial.",
    },
    "headroom": {
        "label": "Espacio de mercado",
        "weight": 1.2,
        "lower_is_better": False,
        "basis": "mixto",
        "description": "Veces que el headroom de mercado cubre la capacidad de la planta.",
    },
    "margin": {
        "label": "Margen unitario",
        "weight": 1.5,
        "lower_is_better": False,
        "basis": "mixto",
        "description": "Margen bruto por kilo sobre el precio FOB de mercado.",
    },
    "capital_intensity": {
        "label": "Intensidad de capital",
        "weight": 1.0,
        "lower_is_better": True,
        "basis": "supuesto",
        "description": "CAPEX sobre la facturación potencial a plena capacidad.",
    },
    "returns": {
        "label": "Retorno (VAN)",
        "weight": 1.5,
        "lower_is_better": False,
        "basis": "supuesto",
        "description": "VAN del proyecto con tus supuestos. Solo vale si están verificados.",
    },
}


def _metric_specs() -> dict[str, dict]:
    """Defaults del codigo + lo que diga config/scoring.yaml (el YAML manda)."""
    specs = {key: dict(value) for key, value in DEFAULT_METRICS.items()}
    for key, metric in load_scoring().metrics.items():
        base = specs.setdefault(key, dict(DEFAULT_METRICS.get(key, {})))
        base.update(metric.model_dump())
    return specs


def _readiness(product, assumptions) -> dict:
    """Que evidencia existe realmente para este producto."""
    files = excel_analysis.data_files_status(product.hs6, product.nandina)
    tariff_rows = manual_tariffs.load_tariffs(product.hs6)
    tariff_known = int(tariff_rows["duty_pct"].notna().sum()) if not tariff_rows.empty else 0
    entry = assumptions.products.get(product.slug)
    return {
        "trademap": files["trademap"],
        "trademap_count": files["trademap_count"],
        "trademap_expected": files["trademap_expected"],
        "sunat": files["sunat"],
        "tariffs_known": tariff_known,
        "tariffs_total": int(len(tariff_rows)),
        "assumptions_present": entry is not None,
        "assumptions_verified": bool(entry.verified) if entry is not None else False,
    }


def _extract(result: dict) -> dict[str, float | None]:
    """Las 7 metricas crudas de un producto ya analizado."""
    market = result.get("market") or {}
    unit = result.get("unit_economics") or {}
    inv = result.get("investment") or {}
    inputs = inv.get("inputs") or {}
    summary = inv.get("summary") or {}
    implied = result.get("implied_volume") or {}
    pricing = result.get("pricing") or {}

    capacity = inputs.get("capacity_kg_year")
    capex = inputs.get("capex_usd")
    fob = pricing.get("price_usd_per_kg") or inputs.get("fob_price_usd_per_kg")

    implied_kg = implied.get("implied_volume_kg")
    installed = implied.get("installed_capacity_kg") or capacity
    headroom = (implied_kg / installed) if (implied_kg is not None and installed) else None

    revenue_potential = (capacity * fob) if (capacity and fob) else None
    capital_intensity = (capex / revenue_potential) if (capex and revenue_potential) else None

    return {
        "market_size": market.get("latest_fob_usd"),
        "growth": market.get("cagr_value"),
        "concentration": market.get("top5_concentration"),
        "headroom": headroom,
        "margin": unit.get("gross_margin_pct"),
        "capital_intensity": capital_intensity,
        "returns": summary.get("npv_usd"),
    }


def _normalize(values: dict[str, float | None], lower_is_better: bool) -> dict[str, float | None]:
    """Min-max a 0-100. Con menos de 2 valores no hay contra que comparar: 50.

    No devuelve error cuando falta un valor: devuelve None para esa metrica y
    el puntaje del producto se calcula con las que si tiene.
    """
    present = [v for v in values.values() if v is not None]
    if len(present) < 2:
        return {key: (50.0 if value is not None else None) for key, value in values.items()}

    low, high = min(present), max(present)
    scores: dict[str, float | None] = {}
    for key, value in values.items():
        if value is None:
            scores[key] = None
        elif high == low:
            scores[key] = 50.0
        else:
            frac = (value - low) / (high - low)
            scores[key] = round((1 - frac if lower_is_better else frac) * 100, 1)
    return scores


def _analyze(slugs: list[str]) -> dict:
    catalog = load_catalog()
    assumptions = load_assumptions()
    specs = _metric_specs()

    products = [get_product(slug) for slug in slugs] if slugs else list(catalog.products)

    entries: list[dict] = []
    for product in products:
        readiness = _readiness(product, assumptions)
        try:
            result = analyze_product(product.slug)
        except Exception as exc:  # noqa: BLE001 - un producto roto no debe tumbar el ranking
            result = {"error": str(exc)}

        market = result.get("market") or {}
        available = bool(market.get("available"))
        entries.append(
            {
                "slug": product.slug,
                "name": product.name,
                "hs6": product.hs6,
                "nandina": product.nandina,
                "available": available,
                "error": result.get("error") or (market.get("message") if not available else None),
                "latest_year": market.get("latest_year"),
                "verdict": (((result.get("investment") or {}).get("summary")) or {}).get("verdict", {}).get("label"),
                "readiness": readiness,
                "values": _extract(result) if available else {key: None for key in specs},
            }
        )

    # Normaliza cada metrica a lo largo de los productos y reparte el puntaje.
    for key, spec in specs.items():
        scores = _normalize(
            {entry["slug"]: entry["values"].get(key) for entry in entries},
            spec["lower_is_better"],
        )
        for entry in entries:
            entry.setdefault("scores", {})[key] = scores[entry["slug"]]

    total_weight = sum(spec["weight"] for spec in specs.values()) or 1.0
    for entry in entries:
        earned = 0.0
        weight_used = 0.0
        for key, spec in specs.items():
            score = entry["scores"].get(key)
            if score is None:
                continue
            earned += score * spec["weight"]
            weight_used += spec["weight"]
        entry["score"] = round(earned / weight_used, 1) if weight_used else None
        entry["score_confidence"] = round(weight_used / total_weight * 100, 0)

    ranked = sorted(
        entries,
        key=lambda entry: (entry["score"] is not None, entry["score"] or 0.0),
        reverse=True,
    )
    for position, entry in enumerate(ranked, start=1):
        entry["rank"] = position if entry["score"] is not None else None

    return {
        "metrics": [{"key": key, **spec} for key, spec in specs.items()],
        "products": ranked,
        "count": len(ranked),
    }


@functools.lru_cache(maxsize=8)
def _cached(slugs: tuple[str, ...]) -> dict:
    return _analyze(list(slugs))


def screen_products(slugs: list[str] | None = None) -> dict:
    """Ranking del catalogo completo (o de los slugs pedidos).

    Memorizado por proceso: correr 15 fichas lee muchos Excel. Los datos son
    estaticos, asi que repetir la llamada no cambia el resultado.
    """
    return _cached(tuple(slugs or ()))
