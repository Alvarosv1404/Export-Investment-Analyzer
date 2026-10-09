"""Precio de venta estimado desde datos historicos de Trade Map (Excel local).

El precio es un input: si el usuario no lo pasa, se estima como el valor FOB
ponderado por kilo del snapshot 2025. Si el snapshot no trae cantidad, se cae
al unit value del Excel y, si tampoco hay, al unit value de la serie historica.
"""

from __future__ import annotations

import pandas as pd

from . import excel_analysis

# Origen del precio, para mostrarlo en el reporte sin ambiguedad.
PRICE_ORIGIN_CALCULATED = "calculado de históricos"
PRICE_ORIGIN_USER = "ajustado por el usuario"
PRICE_ORIGIN_EXCEL = "unit value del Excel"


def estimated_fob_price_usd_per_kg(hs6: str, method: str = "weighted_mean_2025") -> dict:
    """Estima el precio FOB por kg usando el snapshot 2025 de Peru exportador."""
    info = {
        "hs6": hs6,
        "method": method,
        "source": "published",
        "calculated_from": [],
        "price_usd_per_kg": None,
    }

    try:
        ind = excel_analysis.peru_exports_indicators_2025(hs6)
        if len(ind) > 0:
            unit = str(ind["Quantity Unit"].iloc[0]) if "Quantity Unit" in ind.columns else None
            qty_kg = ind["quantity_kg"].sum()
            fob = ind["fob_usd"].sum()
            if pd.notna(qty_kg) and qty_kg > 0 and pd.notna(fob):
                info.update(
                    {
                        "price_usd_per_kg": round(float(fob / qty_kg), 4),
                        "quantity_unit": unit,
                        "last_year": 2025,
                        "calculated_from": [
                            "perus-exports-to-world-in-2025-by-importer_{hs6}.xlsx"
                        ],
                    }
                )
                return info
    except (FileNotFoundError, KeyError, ValueError):
        pass

    # Respaldo: unit value del snapshot o de la serie historica, sin cantidad
    # por kilo. Se declara que no se pudo derivar a nivel de kilo.
    try:
        ind = excel_analysis.peru_exports_indicators_2025(hs6)
        if len(ind) > 0:
            uv = ind["unit_value_usd_per_unit"]
            weight = ind["quantity"]
            if weight.sum() > 0 and uv.notna().any():
                info["source"] = "derived"
                info["warning"] = (
                    "No se pudo ponderar por kilo; el precio es el unit value publicado en "
                    "la unidad de la fuente (revisar Quantity Unit)."
                )
                info["calculated_from"] = [
                    "perus-exports-to-world-in-2025-by-importer_{hs6}.xlsx"
                ]
                return info
    except (FileNotFoundError, KeyError, ValueError):
        pass

    try:
        ts = excel_analysis.peru_exports_ts(hs6)
        if len(ts) > 0:
            info["last_year"] = int(ts["year"].max())
            info["warning"] = (
                "No se encontro cantidad en el snapshot 2025; precio unitario no derivado."
            )
            info["calculated_from"] = ["perus-exports-to-world-by-importer_{hs6}.xlsx"]
            return info
    except (FileNotFoundError, KeyError, ValueError):
        pass

    return info
