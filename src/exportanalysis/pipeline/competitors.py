"""Posicion competitiva: que exportan los otros y cuanto les falta.

El calculo que interesa para decidir invertir no es "el mercado crece", es
"hay espacio que Peru no esta tomando". Eso sale de comparar el share de Peru
en un mercado contra el share de sus vecinos, leyendo el Excel local de
exportadores mundiales (`exporting-economies_<hs6>.xlsx`).

Trade Map publica ahi solo valor (USD Thousand), no volumen. El volumen y el
precio unitario de cada competidor salen del Excel opcional de cantidades
exportadas (`kg_exporting-economies_<hs6>.xlsx`). Si no esta, quedan `None`: es
un dato que la fuente no dio, no un cero.
"""

from __future__ import annotations

import pandas as pd

from . import excel_analysis


def export_comparison(hs6: str, reporter: int, competitors: list[int]) -> pd.DataFrame:
    """Exportaciones del producto por pais competidor, anio a anio."""
    try:
        world = excel_analysis.world_exports(hs6)
    except FileNotFoundError:
        return pd.DataFrame()
    if world.empty:
        return pd.DataFrame()

    # En `exporting-economies` cada fila es un pais exportador con partner=World.
    world = world[world["partnerCd"].astype(int) == 0].copy()
    codes = [reporter, *[c for c in competitors if c != reporter]]
    world["country_code"] = world["reporterCd"].astype(int)
    world = world[world["country_code"].isin(codes)]
    if world.empty:
        return pd.DataFrame()

    grouped = (
        world.groupby(["country_code", "reporterLabel", "year"], as_index=False)
        .agg(value_usd=("fob_usd", "sum"))
        .rename(columns={"reporterLabel": "country"})
    )
    # El groupby se come la bandera; se re-deriva del codigo.
    grouped["is_origin_country"] = grouped["country_code"] == reporter
    grouped = _attach_export_volumes(hs6, grouped)

    totals = grouped.groupby("year")["value_usd"].transform("sum")
    grouped["share"] = grouped["value_usd"] / totals.replace(0, pd.NA)
    return grouped.sort_values(["year", "value_usd"], ascending=[True, False]).reset_index(drop=True)


def _attach_export_volumes(hs6: str, grouped: pd.DataFrame) -> pd.DataFrame:
    """Suma volumen (kg) y precio unitario del Excel de cantidades exportadas.

    La cantidad viene de `kg_exporting-economies_<hs6>.xlsx` (opcional). Si el
    archivo no existe, o el pais/anio no trae cantidad convertible, la columna
    queda vacia: es un hueco de la fuente, no un cero. El precio unitario solo
    se calcula donde hay volumen positivo (`valor / volumen`).
    """
    grouped["volume_kg"] = pd.NA
    grouped["unit_value_usd"] = pd.NA
    try:
        quantities = excel_analysis.world_export_quantities(hs6)
    except FileNotFoundError:
        return grouped
    if quantities.empty:
        return grouped

    quantities = quantities.rename(columns={"reporter_code": "country_code"})
    grouped = grouped.merge(
        quantities[["country_code", "year", "quantity_kg"]],
        on=["country_code", "year"],
        how="left",
    )
    volume = pd.to_numeric(grouped["quantity_kg"], errors="coerce")
    grouped["volume_kg"] = volume
    grouped["unit_value_usd"] = grouped["value_usd"] / volume.where(volume > 0)
    return grouped.drop(columns=["quantity_kg"])


def share_trends(hs6: str, reporter: int, competitors: list[int]) -> dict:
    """Evolucion de la participacion de mercado del pais de origen y su ranking."""
    frame = export_comparison(hs6, reporter, competitors)
    if frame.empty:
        return {"available": False, "message": "Sin datos comparables entre los exportadores."}

    origin = frame[frame["is_origin_country"]]
    if origin.empty:
        return {
            "available": False,
            "message": f"El país de origen (M49 {reporter}) no reporta exportaciones de {hs6}.",
        }

    # El ano de referencia debe ser uno en el que el pais de origen reporte.
    # Tomar el max global deja fuera al pais que nos interesa si tiene un ano
    # de retraso en la publicacion, y el share sale en None sin avisar.
    origin_years = set(origin["year"].dropna().astype(int).tolist())
    all_years = sorted(frame["year"].dropna().astype(int).unique().tolist())
    if origin_years:
        latest_year = max(origin_years)
    elif all_years:
        latest_year = max(all_years)
    else:
        return {"available": False, "message": "Sin años con data."}

    latest = (
        frame[frame["year"] == latest_year]
        .sort_values("value_usd", ascending=False)
        .reset_index(drop=True)
    )
    latest["rank"] = latest.index + 1

    # Cobertura: cuantos de los paises comparados tienen data ese ano. Un share
    # calculado sobre la mitad del mercado subestima el total y por eso el share.
    total_countries = frame["country_code"].nunique()
    reporting = latest["country_code"].nunique()
    coverage = reporting / total_countries if total_countries else 0.0

    origin_latest = latest[latest["is_origin_country"]]
    origin_share = float(origin_latest["share"].iloc[0]) if not origin_latest.empty else None
    origin_rank = int(origin_latest["rank"].iloc[0]) if not origin_latest.empty else None

    # Crecimiento del share = si la tendencia es a ganar o a perder terreno.
    share_series = origin.sort_values("year").set_index("year")["share"].dropna()
    share_change = (
        float(share_series.iloc[-1] - share_series.iloc[0]) if len(share_series) > 1 else None
    )

    return {
        "available": True,
        "latest_year": latest_year,
        "origin_share": origin_share,
        "origin_rank": origin_rank,
        "origin_countries": reporting,
        "compared_countries": total_countries,
        "coverage_pct": coverage * 100,
        "coverage_warning": (
            None
            if coverage >= 0.99
            else (
                f"Solo {reporting} de {total_countries} exportadores comparados reportan "
                f"{latest_year}. El share está calculado sobre ese subconjunto, no sobre "
                "el mercado completo: interprétalo con cuidado."
            )
        ),
        "share_change": share_change,
        "share_trend": (
            "ganando" if share_change and share_change > 0.01
            else "perdiendo" if share_change and share_change < -0.01
            else "estable"
        ),
        "rankings": latest[
            ["country", "country_code", "value_usd", "volume_kg", "share", "unit_value_usd", "rank", "is_origin_country"]
        ].where(pd.notna(latest), None).to_dict("records"),
        # where(notna, None) evita emitir NaN en la serie, que no es JSON valido.
        "series": frame.where(pd.notna(frame), None).to_dict("records"),
    }


def headroom_ladder(
    hs6: str,
    reporter: int,
    competitors: list[int],
    targets: list[float] | None = None,
    unit_value_usd_per_kg: float | None = None,
) -> dict:
    """Espacio de mercado a varios objetivos de participacion, simultaneamente.

    Devolver solo un headroom a un share objetivo es arbitario: elshare objetivo
    no sale de la data, sale de tu apetito por riesgo. Una escalera deja que el
    lector vea el panorama y elija el punto que quiere defender, en vez de
    heredar un numero que eligio otra persona.

    Si se pasa `unit_value_usd_per_kg`, ademas traduce el headroom a kilos, que
    es la unidad que necesita la capacidad instalada.
    """
    trends = share_trends(hs6, reporter, competitors)
    if not trends.get("available"):
        return {"available": False, "message": trends.get("message")}

    market_value = sum(r["value_usd"] for r in trends["rankings"])
    current = trends["origin_share"] or 0.0
    targets = targets or [0.5, 0.6, 0.7, 0.8, 0.9]

    rows = []
    for target in targets:
        gap = max(0.0, target - current)
        usd = gap * market_value
        rows.append(
            {
                "target_share": target,
                "share_gap": gap,
                "headroom_usd": usd,
                "headroom_kg": (usd / unit_value_usd_per_kg) if unit_value_usd_per_kg else None,
                "requires_above_current": gap > 0,
            }
        )

    return {
        "available": True,
        "latest_year": trends["latest_year"],
        "market_value_usd": market_value,
        "current_share": current,
        "coverage_warning": trends.get("coverage_warning"),
        "unit_value_usd_per_kg": unit_value_usd_per_kg,
        "ladder": rows,
        "note": (
            "Cota superior teórica: asume que el crecimiento se le quita a los "
            "exportadores actuales. No modela demanda incremental, obstáculos de "
            "entrada, ni reacción de la competencia."
        ),
    }


def implied_capacity_usd(
    hs6: str,
    reporter: int,
    competitors: list[int],
    target_share: float,
    installed_capacity_kg: float,
    unit_value_usd_per_kg: float | None,
) -> dict:
    """Volumen de negocio que el mercado justificaria, acotado por la capacidad.

    Esto es lo que cierra el circuito entre "el mercado tiene espacio" y "cuanto
    vende el modelo". Sin este paso, el modelo corre con un ramp de ocupacion
    inventado en el config y el analisis de mercado es decorativo.
    """
    ladder = headroom_ladder(
        hs6, reporter, competitors, targets=[target_share], unit_value_usd_per_kg=unit_value_usd_per_kg
    )
    if not ladder.get("available"):
        return {"available": False, "message": ladder.get("message")}

    row = ladder["ladder"][0]
    headroom_usd = row["headroom_usd"]

    if headroom_usd <= 0:
        return {
            "available": True,
            "target_share": target_share,
            "implied_revenue_usd": 0.0,
            "implied_volume_kg": 0.0,
            "installed_capacity_kg": installed_capacity_kg,
            "binds": "market",
            "message": (
                f"Perú ya tiene {ladder['current_share'] * 100:.1f}% del mercado, por encima "
                f"del objetivo de {target_share * 100:.1f}%. Este producto no tiene headroom "
                "de crecimiento con estos parámetros: el caso de inversión, si lo hay, tiene "
                "que apoyarse en otro motivo (penetración en un mercado específico, "
                "diferenciación en precio, o una nueva región), no en ganar share global."
            ),
        }

    implied_kg = headroom_usd / unit_value_usd_per_kg if unit_value_usd_per_kg else None
    if implied_kg is None:
        return {"available": False, "message": "Falta precio unitario para traducir a volumen."}

    # El ramp del modelo nunca puede exceder la capacidad instalada.
    binding = "market" if implied_kg < installed_capacity_kg else "capacity"
    return {
        "available": True,
        "target_share": target_share,
        "implied_revenue_usd": headroom_usd,
        "implied_volume_kg": implied_kg,
        "installed_capacity_kg": installed_capacity_kg,
        "binds": binding,
        "message": (
            "El mercado permite más que la capacidad instalada: el cuello de botella es la "
            "planta, no la demanda. Evalúa ampliar capacidad."
            if binding == "capacity"
            else "El mercado limita el volumen por debajo de la capacidad instalada: "
            "construir más de lo que el mercado sostiene deja capacidad ociosa."
        ),
    }


def default_target_share(hs6: str, reporter: int, competitors: list[int], step: float = 0.02) -> float:
    """Share objetivo por defecto: el actual mas `step` puntos porcentuales.

    Elegir un share objetivo fijo (5% para todos los productos) no tiene
    sentido: para un producto donde Peru ya tiene 20% el objetivo ya esta
    superado, y para uno donde tiene 0.5% seria arbitrariamente conservador.
    Sumar un incremento modesto y uniforme al share real hace que la pregunta
    sea siempre respondible: "que pasa si ganamos un poco mas de lo que
    ganamos el ano pasado?".
    """
    trends = share_trends(hs6, reporter, competitors)
    if not trends.get("available") or trends.get("origin_share") is None:
        return 0.05
    return round(min(0.95, trends["origin_share"] + step), 4)


def world_share_by_year(hs6: str, reporter: int, top_n: int = 9) -> dict:
    """Participación de mercado mundial por año: top N países + resto, destacando Perú."""
    try:
        world = excel_analysis.world_exports(hs6)
    except FileNotFoundError:
        return {"available": False, "message": "No hay datos de exportadores mundiales."}
    if world.empty:
        return {"available": False, "message": "Sin datos comparables entre los exportadores."}

    world = world[world["partnerCd"].astype(int) == 0].copy()
    if world.empty:
        return {"available": False, "message": "Sin datos comparables entre los exportadores."}

    world["country_code"] = world["reporterCd"].astype(int)
    world = world.rename(columns={"reporterLabel": "country"})

    grouped = (
        world.groupby(["country_code", "country", "year"], as_index=False)
        .agg(value_usd=("fob_usd", "sum"))
    )
    grouped["is_origin_country"] = grouped["country_code"] == reporter

    years = sorted(grouped["year"].dropna().astype(int).unique().tolist())
    if not years:
        return {"available": False, "message": "Sin años con data."}

    by_year_list = []
    for year in years:
        df_year = grouped[grouped["year"] == year].copy()
        if df_year.empty:
            continue
        total_usd = float(df_year["value_usd"].sum()) if len(df_year) > 0 else 0.0
        df_year["share"] = df_year["value_usd"] / total_usd if total_usd > 0 else 0.0
        df_year = df_year.sort_values("value_usd", ascending=False).reset_index(drop=True)

        slices = []
        top = df_year.head(top_n).copy()
        for _, row in top.iterrows():
            slices.append(
                {
                    "label": row["country"],
                    "country_code": int(row["country_code"]),
                    "value_usd": float(row["value_usd"]),
                    "share": float(row["share"]),
                    "is_peru": bool(row["is_origin_country"]),
                }
            )

        if len(df_year) > top_n:
            rest_df = df_year.iloc[top_n:].copy()
            rest_value = float(rest_df["value_usd"].sum())
            rest_share = float(rest_df["share"].sum())
            slices.append(
                {
                    "label": f"Resto ({len(rest_df)} países)",
                    "country_code": None,
                    "value_usd": rest_value,
                    "share": rest_share,
                    "is_peru": False,
                }
            )

        peru_row = df_year[df_year["is_origin_country"]]
        peru_info = {}
        if not peru_row.empty:
            peru_pos = int(peru_row.index[0] + 1)
            peru_info = {
                "in_top": peru_pos <= top_n,
                "rank": peru_pos,
                "share": float(peru_row["share"].iloc[0]),
                "value_usd": float(peru_row["value_usd"].iloc[0]),
            }

        by_year_list.append(
            {
                "year": int(year),
                "total_usd": total_usd,
                "countries_with_data": int(len(df_year)),
                "slices": slices,
                "peru": peru_info,
            }
        )

    return {
        "available": True,
        "years": years,
        "by_year": by_year_list,
        "top_n": top_n,
    }
