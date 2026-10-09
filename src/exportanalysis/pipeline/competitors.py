"""Posicion competitiva: que exportan los otros y cuanto les falta.

El calculo que interesa para decidir invertir no es "el mercado crece", es
"hay espacio que Peru no esta tomando". Eso sale de comparar el share de Peru
en un mercado contra el share de sus vecinos.
"""

from __future__ import annotations

import pandas as pd

from ..sources import comtrade


def export_comparison(hs6: str, reporter: int, competitors: list[int]) -> pd.DataFrame:
    """Exportaciones del producto por pais competidor, anio a anio."""
    codes = [reporter, *[c for c in competitors if c != reporter]]
    frames = [comtrade.fetch_trade(hs6, reporter=code, flow="X", partner=0) for code in codes]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out = out[out["is_world"]]
    out = out.rename(columns={"reporter_name": "country", "reporter_code": "country_code"})
    out["is_origin_country"] = out["country_code"] == reporter

    grouped = (
        out.groupby(["country_code", "country", "year"], as_index=False)
        .agg(value_usd=("fob_usd", "sum"), volume_kg=("net_weight_kg", "sum"))
    )
    # El groupby se come la columna de bandera: se re-deriva del codigo.
    grouped["is_origin_country"] = grouped["country_code"] == reporter

    totals = grouped.groupby("year")["value_usd"].transform("sum")
    grouped["share"] = grouped["value_usd"] / totals.replace(0, pd.NA)
    grouped["unit_value_usd"] = grouped["value_usd"] / grouped["volume_kg"].replace(0, pd.NA)
    return grouped.sort_values(["year", "value_usd"], ascending=[True, False]).reset_index(drop=True)


def share_trends(hs6: str, reporter: int, competitors: list[int]) -> dict:
    """Evolucion de la participacion de mercado del pais de origen y su ranking."""
    frame = export_comparison(hs6, reporter, competitors)
    if frame.empty:
        return {"available": False, "message": "Sin datos comparables entre los exportadores."}

    origin = frame[frame["is_origin_country"]]
    if origin.empty:
        return {
            "available": False,
            "message": f"El pais de origen (M49 {reporter}) no reporta exportaciones de {hs6}.",
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
        return {"available": False, "message": "Sin anos con data."}

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
                f"{latest_year}. El share esta calculado sobre ese subconjunto, no sobre "
                "el mercado completo: interpretalo con cuidado."
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
    targets = targets or [0.05, 0.075, 0.10, 0.125, 0.15]

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
            "Cota superior teorica: asume que el crecimiento se le quita a los "
            "exportadores actuales. No modela demanda incremental, obstaculos de "
            "entrada, ni reaccion de la competencia."
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
                f"Peru ya tiene {ladder['current_share'] * 100:.1f}% del mercado, por encima "
                f"del objetivo de {target_share * 100:.1f}%. Este producto no tiene headroom "
                "de crecimiento con estos parametros: el caso de inversion, si lo hay, tiene "
                "que apoyarse en otro motivo (penetracion en un mercado especifico, "
                "diferenciacion en precio, o una nueva region), no en ganar share global."
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
            "El mercado permite mas que la capacidad instalada: el cuello de botella es la "
            "planta, no la demanda. Evalua ampliar capacidad."
            if binding == "capacity"
            else "El mercado limita el volumen por debajo de la capacidad instalada: "
            "construir mas de lo que el mercado sostiene deja capacidad ociosa."
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
