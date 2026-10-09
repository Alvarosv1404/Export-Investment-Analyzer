"""Comparacion entre productos usando series historicas completas."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import get_product, load_catalog
from . import excel_analysis


def _cagr(series: pd.Series) -> float | None:
    s = series.dropna().astype(float)
    if len(s) < 2:
        return None
    first = float(s.iloc[0])
    last = float(s.iloc[-1])
    if first <= 0 or last <= 0:
        return None
    n = len(s) - 1
    if n <= 0:
        return None
    try:
        return (last / first) ** (1.0 / n) - 1.0
    except Exception:
        return None


def _volatility(series: pd.Series) -> float | None:
    s = series.dropna().astype(float).pct_change().dropna()
    if len(s) < 2:
        return None
    return float(s.std())


def _get_product_hs6(slug: str) -> str:
    try:
        p = get_product(slug)
        return p.hs6
    except Exception:
        return slug


def _series_product(slug: str) -> dict[str, Any]:
    hs6 = _get_product_hs6(slug)
    try:
        df = excel_analysis.peru_exports_ts(hs6)
    except Exception:
        return {
            "slug": slug,
            "hs6": hs6,
            "available": False,
            "error": "No se pudieron leer datos del producto",
        }

    df = df.copy()
    # totals by year
    g = df.groupby("year", as_index=False).agg(
        fob_usd=("fob_usd", "sum"),
    )
    g = g.sort_values("year")

    # try to get quantity if available
    try:
        d2 = excel_analysis.peru_exports_ts_with_quantity(hs6)
        gq = d2.groupby("year", as_index=False).agg(
            quantity=("quantity", "sum"),
        )
        g = g.merge(gq, on="year", how="left")
    except Exception:
        g["quantity"] = pd.NA

    g["unit_value_usd"] = np.where(
        g["quantity"].notna() & (g["quantity"] > 0),
        g["fob_usd"] / g["quantity"],
        pd.NA,
    )

    # concentration - top destination share by latest year
    latest_year = int(g["year"].max()) if len(g) > 0 else None
    conc = None
    peru_rank = None
    if latest_year is not None and len(df) > 0:
        dly = df[df["year"] == latest_year]
        if len(dly) > 0:
            total = dly["fob_usd"].sum()
            top5 = dly.nlargest(5, "fob_usd")["fob_usd"].sum()
            conc = (top5 / total) if total > 0 else None
            # peru rank in global? not directly - keep None or could compute from world

    return {
        "slug": slug,
        "hs6": hs6,
        "available": True,
        "years": g["year"].tolist(),
        "series": g.where(pd.notna(g), None).to_dict("records"),
        "cagr_value": _cagr(g["fob_usd"]),
        "cagr_volume": _cagr(g["quantity"]),
        "cagr_unit_value": _cagr(g["unit_value_usd"]),
        "volatility_value": _volatility(g["fob_usd"]),
        "volatility_unit_value": _volatility(g["unit_value_usd"]),
        "concentration_top5": conc,
        "latest_year": latest_year,
        "peru_rank": peru_rank,
    }


def compare_products(slugs: list[str]) -> dict[str, Any]:
    slugs = [s for s in slugs if s]
    products = [_series_product(s) for s in slugs]
    return {
        "products": products,
        "available_count": sum(1 for p in products if p.get("available")),
    }


def all_product_slugs() -> list[str]:
    cat = load_catalog()
    return [p.slug for p in cat.products]
