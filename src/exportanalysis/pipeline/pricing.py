"""Calculo de precio de venta estimado desde datos historicos (Excel)."""

from __future__ import annotations

import pandas as pd

from . import excel_analysis


def _to_usd_per_kg(val: float | None, unit: str | None = None) -> float | None:
    if val is None or pd.isna(val):
        return None
    unit = (unit or "").lower()
    # Trade Map suele dar "Tons" o "t"
    if "ton" in unit or unit == "t":
        return float(val) / 1000.0
    return float(val)


def estimated_fob_price_usd_per_kg(hs6: str, method: str = "weighted_mean_2025") -> dict:
    """Estima precio FOB por kg usando indicadores 2025 y serie historica."""
    info = {"hs6": hs6, "method": method, "source": "published", "calculated_from": []}

    try:
        ind = excel_analysis.peru_exports_indicators_2025(hs6)
        if len(ind) > 0:
            unit = str(ind["Quantity Unit"].iloc[0]) if "Quantity Unit" in ind.columns else None
            # weighted mean by quantity from total
            qty = ind["quantity"].sum()
            fob = ind["fob_usd"].sum()
            if pd.notna(qty) and qty > 0 and pd.notna(fob):
                wavg = fob / qty  # per original unit
                p = _to_usd_per_kg(wavg, unit)
                info.update(
                    {
                        "price_usd_per_kg": round(float(p), 4) if p else None,
                        "quantity_unit": unit,
                        "last_year": 2025,
                        "calculated_from": ["perus-indicadores-exports-to-world-in-2025-by-importer_{hs6}.xlsx"],
                    }
                )
                return info
    except Exception:
        pass

    # fallback: use peru_exports_ts (no qty) - cannot get good unit price; return None
    try:
        ts = excel_analysis.peru_exports_ts(hs6)
        if len(ts) > 0:
            last = int(ts["year"].max())
            info["last_year"] = last
            info["warning"] = "No se encontro cantidad en indicadores 2025; precio unitario no derivado directamente"
            info["calculated_from"] = ["perus-exports-to-world-by-importer_{hs6}.xlsx"]
            info["price_usd_per_kg"] = None
            return info
    except Exception:
        pass

    info["price_usd_per_kg"] = None
    return info
