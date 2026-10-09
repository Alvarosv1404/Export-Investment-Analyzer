"""Metricas de mercado: tamaño, crecimiento, precio y concentracion.

Todo lo que se deriva de la data de Trade Map (Excel local). No inventado: cada
numero sale de una serie publicada. Lo que NO se puede derivar de la data
(arancel, flete real, costo propio) vive en otras capas y se marca como
supuesto.

Las funciones reciben DataFrames ya normalizados por
`pipeline.excel_analysis`; no consultan la red.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def annual_totals(trade: pd.DataFrame) -> pd.DataFrame:
    """Serie anual del total (partner 'World'), con precio unitario y CAGR."""
    totals = (
        trade[trade["is_world"]]
        .groupby("year", as_index=False)
        .agg(
            fob_usd=("fob_usd", "sum"),
            # min_count=1 conserva el hueco real: un anio sin volumen publicado
            # queda en NaN, no en 0. Un 0 se leeria como "no se exporto nada".
            volume_kg=("net_weight_kg", lambda s: s.sum(min_count=1)),
        )
        .sort_values("year")
        .reset_index(drop=True)
    )
    if totals.empty:
        return totals

    totals["unit_value_usd"] = np.where(
        totals["volume_kg"].fillna(0) > 0, totals["fob_usd"] / totals["volume_kg"], np.nan
    )
    totals["value_yoy"] = totals["fob_usd"].pct_change()
    totals["volume_yoy"] = totals["volume_kg"].pct_change()
    totals["unit_value_yoy"] = totals["unit_value_usd"].pct_change()
    return totals


def cagr(series: pd.Series, periods: int | None = None) -> float | None:
    """CAGR de una serie de valores usd/kg/ton. None si no se puede calcular."""
    clean = series.dropna()
    if len(clean) < 2:
        return None
    first, last = float(clean.iloc[0]), float(clean.iloc[-1])
    if first <= 0 or last <= 0:
        return None
    n = periods if periods is not None else len(clean) - 1
    if n <= 0:
        return None
    return float((last / first) ** (1 / n) - 1)


def market_summary(trade: pd.DataFrame) -> dict:
    """Resumen ejecutivo del mercado: totales, CAGR, precio, participacion."""
    totals = annual_totals(trade)
    if totals.empty:
        return {
            "available": False,
            "message": "Sin datos de comercio para este producto y ventana de anos.",
        }

    latest = totals.iloc[-1]
    previous = totals.iloc[-2] if len(totals) > 1 else None
    countries = trade[~trade["is_world"]]
    latest_year = int(latest["year"])

    top = (
        countries[countries["year"] == latest_year]
        .nlargest(10, "fob_usd")[["partner_name", "fob_usd", "net_weight_kg"]]
        .to_dict("records")
    ) if not countries.empty else []

    top5_value = sum(r["fob_usd"] or 0 for r in top[:5])
    latest_value = float(latest["fob_usd"] or 0)

    return {
        "available": True,
        "latest_year": latest_year,
        "latest_fob_usd": latest_value,
        "latest_volume_kg": (
            float(latest["volume_kg"]) if pd.notna(latest["volume_kg"]) else None
        ),
        "latest_unit_value_usd": (
            float(latest["unit_value_usd"]) if pd.notna(latest["unit_value_usd"]) else None
        ),
        "cagr_value": cagr(totals["fob_usd"]),
        "cagr_volume": cagr(totals["volume_kg"]),
        "cagr_unit_value": cagr(totals["unit_value_usd"]),
        "value_yoy": (
            float(previous["value_yoy"]) if previous is not None and pd.notna(previous["value_yoy"]) else None
        ),
        "unit_value_yoy": (
            float(previous["unit_value_yoy"])
            if previous is not None and pd.notna(previous["unit_value_yoy"])
            else None
        ),
        "top_destinations": top,
        "top5_concentration": (top5_value / latest_value) if latest_value > 0 else None,
        # where(notna, x, None) convierte el NaN del primer anio (pct_change sin
        # ano previo) en null. Sin esto, el dict lleva NaN y la serializacion a
        # JSON revienta: NaN no es null, es un valor que JSON no admite.
        "series": totals.where(pd.notna(totals), None).to_dict("records"),
    }


def destination_breakdown(trade: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Ranking de destinos del ultimo anio con data, con precios y participacion."""
    if trade.empty:
        return pd.DataFrame()

    years = sorted(trade["year"].dropna().unique().tolist())
    year = year or (years[-1] if years else None)
    if year is None:
        return pd.DataFrame()

    frame = trade[(trade["year"] == year) & (~trade["is_world"])].copy()
    if frame.empty:
        return pd.DataFrame()

    total = frame["fob_usd"].sum()
    frame = frame.groupby(["partner_code", "partner_name"], as_index=False).agg(
        fob_usd=("fob_usd", "sum"),
        volume_kg=("net_weight_kg", lambda s: s.sum(min_count=1)),
    )
    frame["share"] = frame["fob_usd"] / total if total else np.nan
    frame["unit_value_usd"] = np.where(
        frame["volume_kg"].fillna(0) > 0, frame["fob_usd"] / frame["volume_kg"], np.nan
    )
    frame["year"] = year
    return frame.sort_values("fob_usd", ascending=False).reset_index(drop=True)
