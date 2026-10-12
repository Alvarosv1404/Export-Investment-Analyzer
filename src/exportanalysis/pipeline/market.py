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
            "message": "Sin datos de comercio para este producto y ventana de años.",
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
    dest_df = destination_breakdown(trade, latest_year)
    hhi_info = calculate_hhi(dest_df["share"]) if not dest_df.empty else {"hhi": None, "category": "Sin datos", "interpretation": ""}

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
        "volume_yoy": (
            float(previous["volume_yoy"]) if previous is not None and pd.notna(previous["volume_yoy"]) else None
        ),
        "unit_value_yoy": (
            float(previous["unit_value_yoy"])
            if previous is not None and pd.notna(previous["unit_value_yoy"])
            else None
        ),
        "top_destinations": top,
        "top5_concentration": (top5_value / latest_value) if latest_value > 0 else None,
        "hhi": hhi_info.get("hhi"),
        "hhi_category": hhi_info.get("category"),
        "hhi_interpretation": hhi_info.get("interpretation"),
        # where(notna, x, None) convierte el NaN del primer anio (pct_change sin
        # ano previo) en null. Sin esto, el dict lleva NaN y la serializacion a
        # JSON revienta: NaN no es null, es un valor que JSON no admite.
        "series": totals.where(pd.notna(totals), None).to_dict("records"),
    }


def _series_cagr(years: pd.Series, values: pd.Series) -> float | None:
    valid = pd.DataFrame({"year": years, "value": values}).dropna().sort_values("year")
    if len(valid) < 2:
        return None
    first = float(valid.iloc[0]["value"])
    last = float(valid.iloc[-1]["value"])
    periods = int(valid.iloc[-1]["year"] - valid.iloc[0]["year"])
    if first <= 0 or last <= 0 or periods <= 0:
        return None
    return float((last / first) ** (1 / periods) - 1)


def import_demand_summary(values: pd.DataFrame, quantities: pd.DataFrame) -> dict:
    """Demanda importadora por destino con valor CIF y cantidad observados."""
    if values.empty or quantities.empty:
        return {"available": False, "destinations": []}

    imports = values.copy()
    imports["reporter_code"] = pd.to_numeric(imports["reporterCd"], errors="coerce").astype(
        "Int64"
    )
    imports["partner_code"] = pd.to_numeric(imports["partnerCd"], errors="coerce")
    imports = imports[(imports["partner_code"] == 0) & (imports["reporter_code"] != 0)]
    imports = imports[["reporter_code", "reporterLabel", "year", "cif_usd"]]

    merged = imports.merge(
        quantities,
        on=["reporter_code", "year"],
        how="inner",
        validate="one_to_one",
    )
    merged = merged.dropna(subset=["cif_usd", "quantity_kg"])
    merged = merged[(merged["cif_usd"] > 0) & (merged["quantity_kg"] > 0)].copy()
    if merged.empty:
        return {"available": False, "destinations": []}

    merged["unit_value_usd_per_kg"] = merged["cif_usd"] / merged["quantity_kg"]
    latest_year = int(merged["year"].max())
    latest = (
        merged[merged["year"] == latest_year]
        .sort_values("cif_usd", ascending=False)
        .head(8)
    )

    destinations: list[dict] = []
    for row in latest.itertuples(index=False):
        history = merged[merged["reporter_code"] == row.reporter_code].sort_values("year")
        destinations.append(
            {
                "reporter_code": int(row.reporter_code),
                "country": str(row.reporterLabel),
                "year": latest_year,
                "import_value_usd": float(row.cif_usd),
                "import_quantity_kg": float(row.quantity_kg),
                "unit_value_usd_per_kg": float(row.unit_value_usd_per_kg),
                "cagr_value": _series_cagr(history["year"], history["cif_usd"]),
                "cagr_quantity": _series_cagr(history["year"], history["quantity_kg"]),
                "quantity_first_year": int(history["year"].min()),
            }
        )

    return {
        "available": True,
        "latest_year": latest_year,
        "destination_count": int(merged.loc[merged["year"] == latest_year, "reporter_code"].nunique()),
        "destinations": destinations,
        "source": "Trade Map (Excel local: importaciones CIF y cantidades por destino)",
    }


def calculate_hhi(shares: pd.Series | list[float]) -> dict:
    """Calcula el Índice Herfindahl-Hirschman (HHI) y su nivel de concentración.

    HHI = sum((share_pct)^2). Rango: 0 a 10,000 puntos.
    Interpretación estándar DOJ/FTC:
      - HHI < 1,500: Baja concentración / Mercado diversificado.
      - 1,500 <= HHI <= 2,500: Concentración moderada.
      - HHI > 2,500: Alta concentración / Riesgo de dependencia de clientes o destinos.
    """
    s = pd.Series(shares).dropna()
    if s.empty:
        return {"hhi": None, "category": "Sin datos", "interpretation": "Sin datos suficientes"}
    # Si las fracciones estan en [0, 1], convertir a porcentaje [0, 100]
    pct = s * 100.0 if s.max() <= 1.0 else s
    hhi = float((pct ** 2).sum())
    hhi = round(hhi, 1)

    if hhi < 1500:
        category = "Baja concentración"
        interpretation = "Mercado diversificado: bajo riesgo comercial de concentración."
    elif hhi <= 2500:
        category = "Concentración moderada"
        interpretation = "Mercado con concentración moderada: requiere seguimiento de socios clave."
    else:
        category = "Alta concentración"
        interpretation = "Mercado altamente concentrado: alta dependencia de pocos destinos de exportación."

    return {
        "hhi": hhi,
        "category": category,
        "interpretation": interpretation,
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


_SUPERSCRIPTS = {1: "", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸"}


def _poly_equation(coeffs, center: int) -> str:
    """Ecuacion legible del polinomio, en terminos de t = (anio - center).

    Los coeficientes de np.polyfit vienen de grado mayor a menor. Se expresa con
    t relativo al centro porque con anios grandes (2016...) los coeficientes
    salen minusculos e ilegibles; centrar los deja interpretables y, de paso,
    hace el ajuste numericamente mas estable.
    """
    deg = len(coeffs) - 1
    terms: list[str] = []
    for i, c in enumerate(coeffs):
        power = deg - i
        if abs(c) < 1e-12:
            continue
        sup = _SUPERSCRIPTS.get(power, f"^{power}")
        tvar = "t" if power == 1 else ("" if power == 0 else f"t{sup}")
        coef = f"{abs(c):.4g}"
        sign = "+" if c >= 0 else "−"
        if power == 0:
            terms.append(f"{sign} {coef}")
        else:
            terms.append(f"{sign} {coef}{tvar}")
    if not terms:
        return "y = 0"
    eq = " ".join(terms).lstrip("+ ").strip()
    return f"y = {eq}   (t = año − {center})"


def trend_projection(
    series: list[dict],
    *,
    value_key: str = "fob_usd",
    degree: int = 2,
    forecast_years: int = 3,
) -> dict:
    """Ajuste polinomial por minimos cuadrados + extrapolacion a futuro.

    Responde "como podria seguir la exportacion" con la evidencia que ya hay:
    ajusta una curva a la serie historica y la extiende unos anos. No es un
    oraculo: es la continuacion de la tendencia, util para intuir escenarios.

    El ano se centra (t = anio - media) antes de ajustar: con anios de 4 digitos
    los coeficientes salen tan pequenos que el ajuste pierde precision y la
    ecuacion es ilegible. Grado 2 (cuadratico) es el default porque extrapola
    estable; grados mas altos suben el R2 historico pero su extrapolacion se
    descontrola (un grado 3 puede caer a cero en la proyeccion aunque ajuste
    casi perfecto el pasado).

    Devuelve la serie historica, la linea de tendencia sobre esos mismos anos,
    los puntos proyectados a futuro, la ecuacion y el R².
    """
    pts = [
        (int(r["year"]), float(r[value_key]))
        for r in series
        if r.get("year") is not None and r.get(value_key) is not None
    ]
    pts = [(y, v) for y, v in pts if np.isfinite(v)]
    if len(pts) < degree + 1:
        return {
            "available": False,
            "message": (
                f"Hacen falta al menos {degree + 1} años con dato para proyectar "
                f"una tendencia de grado {degree}."
            ),
        }


    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)
    center = int(round(float(xs.mean())))
    t = xs - center

    coeffs = np.polyfit(t, ys, degree)
    poly = np.poly1d(coeffs)

    historical = [{"year": int(x), "value": float(y)} for x, y in zip(xs, ys, strict=True)]
    trend = [{"year": int(x), "value": float(poly(ti))} for x, ti in zip(xs, t, strict=True)]

    last_year = int(xs.max())
    future_xs = [last_year + i for i in range(1, forecast_years + 1)]
    forecast = [
        {"year": int(fx), "value": float(poly(fx - center))} for fx in future_xs
    ]

    y_mean = float(ys.mean())
    ss_res = float(np.sum((ys - poly(t)) ** 2))
    ss_tot = float(np.sum((ys - y_mean) ** 2))
    r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else None

    return {
        "available": True,
        "degree": degree,
        "center": center,
        "forecast_years": future_xs,
        "historical": historical,
        "trend": trend,
        "forecast": forecast,
        "equation": _poly_equation(coeffs, center),
        "r_squared": round(r2, 4) if r2 is not None else None,
    }


def moving_average_projection(
    series: list[dict],
    *,
    value_key: str = "fob_usd",
    window: int = 3,
    forecast_years: int = 2,
) -> dict:
    """Proyecta con el promedio móvil simple de los últimos años consecutivos."""
    points = {
        int(row["year"]): float(row[value_key])
        for row in series
        if row.get("year") is not None
        and row.get(value_key) is not None
        and np.isfinite(float(row[value_key]))
    }
    historical = [{"year": year, "value": value} for year, value in sorted(points.items())]
    if len(points) < window:
        return {
            "available": False,
            "message": f"Hacen falta {window} años con dato para calcular la media móvil.",
        }

    last_year = max(points)
    window_years = list(range(last_year - window + 1, last_year + 1))
    if any(year not in points for year in window_years):
        return {
            "available": False,
            "message": (
                f"La proyección requiere {window} años consecutivos con datos "
                "al final de la serie."
            ),
        }

    average = float(np.mean([points[year] for year in window_years]))
    trend = []
    for year in sorted(points):
        years = list(range(year - window + 1, year + 1))
        if all(item in points for item in years):
            trend.append({"year": year, "value": float(np.mean([points[item] for item in years]))})
    forecast = [
        {"year": last_year + step, "value": average}
        for step in range(1, forecast_years + 1)
    ]

    return {
        "available": True,
        "method": "media móvil simple",
        "window": window,
        "window_years": window_years,
        "forecast_years": [row["year"] for row in forecast],
        "historical": historical,
        "trend": trend,
        "forecast": forecast,
        "average_value": average,
    }
