"""Adaptador de UN Comtrade (API publica, sin key).

VERIFICADO 2026-09-30 contra la API real:
    GET https://comtradeapi.un.org/public/v1/preview/C/A/HS
        ?reporterCode=604&period=2023&cmdCode=090111&flowCode=X
    -> 200, 56 registros (Peru, cafe verde 2023, todos los destinos)

Notas importantes que costaron tiempo descubrir:
  - `period` NO acepta lista de anos en el endpoint publico: devuelve 400.
    Hay que iterar ano por ano. El pipeline lo hace asi a proposito.
  - La API publica tiene limite de ~500 registros por consulta. Al filtrar por
    un solo cmdCode y un solo anio no se llega a ese techo; el riesgo real
    aparece al pedir todo un chapter (4 digitos) para todos los partners.
  - El endpoint `preview` devuelve `partnerDesc = null`. Los nombres de pais
    salen del archivo de referencia `partnerAreas.json` (ver `country_map`).
  - Limite de tasa real: ~1.5s entre llamadas, o responde 429. Ver .env.example.
  - `comtrade.un.org/api/get` (el endpoint viejo) ya no sirve: devuelve HTML.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

from ..cache import build_session, fetch_json
from ..config import country_name

log = logging.getLogger(__name__)

BASE = "https://comtradeapi.un.org/public/v1/preview"
REFERENCE_URL = "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
MAX_RECORDS = 500


def _sleep() -> float:
    return float(os.getenv("COMTRADE_SLEEP", "1.5"))


def last_complete_year() -> int:
    """Ultimo anio con estadisticas anuales consolidadas.

    Comtrade publica el anio en curso a medias y con revisiones, asi que para
    un analisis de decision conviene cerrar en n-1.
    """
    return date.today().year - 1


def year_window(years: int) -> list[int]:
    """Ultimos `years` anos completos, ordenados."""
    end = last_complete_year()
    return list(range(end - years + 1, end + 1))


def country_map(session: requests.Session | None = None) -> dict[int, str]:
    """Codigo M49 -> nombre de pais, desde el archivo de referencia de Comtrade."""
    payload = fetch_json(REFERENCE_URL, namespace="comtrade_ref", session=session)
    return {int(row["id"]): row["text"] for row in payload.get("results", [])}


def _request(
    session: requests.Session,
    *,
    reporter: int,
    year: int,
    cmd_code: str,
    flow: str,
    partner: int | None,
) -> list[dict[str, Any]]:
    params = {
        "reporterCode": reporter,
        "period": year,
        "cmdCode": cmd_code,
        "flowCode": flow,
        "partner2Code": 0,
        "customsCode": "C00",
        "motCode": 0,
        "maxRecords": MAX_RECORDS,
    }
    # partner ausente => todos los socios. partner=0 => total mundo.
    if partner is not None:
        params["partnerCode"] = partner

    url = f"{BASE}/C/A/HS?{urlencode(params)}"
    payload = fetch_json(
        url,
        namespace="comtrade",
        session=session,
        sleep=_sleep(),
        max_age_hours=24 * 30,  # el historico no cambia; 30 dias es un refresher seguro
    )
    return payload.get("data") or []


def _to_frame(rows: list[dict[str, Any]], reporters: dict[int, str] | None = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame["year"] = pd.to_numeric(frame["period"], errors="coerce").astype("Int64")
    frame["partner_code"] = pd.to_numeric(frame["partnerCode"], errors="coerce").astype("Int64")
    frame["fob_usd"] = pd.to_numeric(frame.get("primaryValue"), errors="coerce")
    frame["net_weight_kg"] = pd.to_numeric(frame.get("netWgt"), errors="coerce")
    frame["gross_weight_kg"] = pd.to_numeric(frame.get("grossWgt"), errors="coerce")
    frame["quantity"] = pd.to_numeric(frame.get("qty"), errors="coerce")
    frame["quantity_unit"] = frame.get("qtyUnitAbbr")
    frame["reporter_code"] = pd.to_numeric(frame["reporterCode"], errors="coerce").astype("Int64")

    # partnerDesc llega null en el endpoint preview, por eso el mapa de referencia.
    # Se prefieren los nombres de countries.yaml (en español) y se cae a la
    # referencia de Comtrade (en inglés) para los paises no listados ahi.
    spanish = frame["partner_code"].map(country_name)
    unknown = spanish.eq([f"codigo {c}" for c in frame["partner_code"]])
    english = frame["partner_code"].map(reporters)
    frame["partner_name"] = spanish.mask(unknown, english).fillna(spanish)

    # El total "World" (partner 0) no es un pais: se separa para no contaminar
    # los calculos de participacion de mercado.
    frame["is_world"] = frame["partner_code"] == 0

    keep = [
        "year",
        "reporter_code",
        "partner_code",
        "partner_name",
        "is_world",
        "fob_usd",
        "net_weight_kg",
        "gross_weight_kg",
        "quantity",
        "quantity_unit",
    ]
    return frame[keep].sort_values(["year", "fob_usd"], ascending=[True, False]).reset_index(drop=True)


def fetch_trade(
    hs6: str,
    *,
    reporter: int = 604,
    flow: str = "X",
    years: list[int] | None = None,
    partner: int | None = None,
) -> pd.DataFrame:
    """Serie de comercio de un producto, por socio y anio.

    reporter: codigo M49 de quien reporta (604 = Peru)
    flow:     "X" exportaciones, "M" importaciones
    partner:  M49 de un socio especifico, o None para todos
    years:    lista de anos. Por defecto, los ultimos 5 completos.
    """
    years = years or year_window(5)
    session = build_session(retries=int(os.getenv("COMTRADE_MAX_RETRIES", "5")))
    names = country_map(session)

    frames = []
    for year in years:
        try:
            rows = _request(
                session,
                reporter=reporter,
                year=year,
                cmd_code=hs6,
                flow=flow,
                partner=partner,
            )
        except requests.HTTPError as exc:
            log.error("Comtrade fallo hs6=%s year=%s: %s", hs6, year, exc)
            continue
        if not rows:
            log.warning("Sin datos hs6=%s reporter=%s year=%s", hs6, reporter, year)
            continue
        frames.append(_to_frame(rows, names))

    if not frames:
        return pd.DataFrame(
            columns=[
                "year", "reporter_code", "partner_code", "partner_name", "is_world",
                "fob_usd", "net_weight_kg", "gross_weight_kg", "quantity", "quantity_unit",
            ]
        )

    out = pd.concat(frames, ignore_index=True)
    out["hs6"] = hs6
    out["flow"] = flow
    out["reporter_name"] = out["reporter_code"].map(names).fillna(
        out["reporter_code"].map(country_name)
    )
    return out


def world_total(hs6: str, *, reporter: int = 604, years: list[int] | None = None) -> pd.DataFrame:
    """Valor total exportado/importado por el reporter, serie anual."""
    frame = fetch_trade(hs6, reporter=reporter, flow="X", years=years, partner=0)
    return frame[frame["is_world"]][["year", "fob_usd", "net_weight_kg"]].reset_index(drop=True)


def competitor_shares(
    hs6: str,
    *,
    competitors: list[int],
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Exportaciones del producto, desagregadas por pais competidor, en un solo DataFrame."""
    frames = []
    for code in competitors:
        frame = fetch_trade(hs6, reporter=code, flow="X", years=years, partner=0)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out["is_competitor"] = True
    out["value_usd"] = out["fob_usd"]
    out["volume_kg"] = out["net_weight_kg"]
    return out[["reporter_code", "reporter_name", "year", "value_usd", "volume_kg", "is_competitor"]]
