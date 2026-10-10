"""Comparacion entre productos usando series historicas completas."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import get_product, load_catalog
from . import excel_analysis

BASE_YEAR = 2016
END_YEAR = 2025


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


def _period_cagr(frame: pd.DataFrame, start_year: int, end_year: int) -> float | None:
    values = frame.set_index("year")["fob_usd"]
    if start_year not in values.index or end_year not in values.index:
        return None
    first = values.loc[start_year]
    last = values.loc[end_year]
    if pd.isna(first) or pd.isna(last) or first <= 0 or last < 0:
        return None
    return float((last / first) ** (1.0 / (end_year - start_year)) - 1.0)


def _volatility(series: pd.Series) -> float | None:
    s = series.dropna().astype(float).pct_change().dropna()
    if len(s) < 2:
        return None
    return float(s.std())


def _series_product(slug: str) -> dict[str, Any]:
    try:
        product = get_product(slug)
        hs6 = product.hs6
        name = product.name
    except KeyError:
        hs6 = slug
        name = slug

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
    g = (
        g.set_index("year")
        .reindex(range(BASE_YEAR, END_YEAR + 1))
        .rename_axis("year")
        .reset_index()
    )
    base_value = g.loc[g["year"] == BASE_YEAR, "fob_usd"].iloc[0]
    g["value_yoy"] = g["fob_usd"].pct_change(fill_method=None)
    g["cagr_from_2016"] = [
        float((value / base_value) ** (1.0 / (year - BASE_YEAR)) - 1.0)
        if year > BASE_YEAR
        and pd.notna(base_value)
        and base_value > 0
        and pd.notna(value)
        and value >= 0
        else None
        for year, value in zip(g["year"], g["fob_usd"], strict=False)
    ]

    # concentration - top destination share by latest year
    observed_years = g.loc[g["fob_usd"].notna(), "year"]
    latest_year = int(observed_years.max()) if not observed_years.empty else None
    conc = None
    peru_rank = None
    if latest_year is not None and len(df) > 0:
        dly = df[df["year"] == latest_year]
        if len(dly) > 0:
            total = dly["fob_usd"].sum()
            top5 = dly.nlargest(5, "fob_usd")["fob_usd"].sum()
            conc = (top5 / total) if total > 0 else None
            # peru rank in global? not directly - keep None or could compute from world

    series = []
    for row in g.to_dict("records"):
        series.append(
            {
                key: None if pd.isna(value) else value.item() if isinstance(value, np.generic) else value
                for key, value in row.items()
            }
        )

    return {
        "slug": slug,
        "name": name,
        "hs6": hs6,
        "available": True,
        "years": list(range(BASE_YEAR, END_YEAR + 1)),
        "series": series,
        "cagr_value": _period_cagr(g, BASE_YEAR, END_YEAR),
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
