"""Scraper de SUNAT / Aduanet: exportaciones acumuladas por subpartida y pais.

ESTADO: EL BACKEND DEVUELVE VACIO. Verificado 2026-09-30.

La herramienta oficial "Acumulado anual subpartida nacional/pais"
(http://www.aduanet.gob.pe/cl-ad-itestadispartida/resumenPPaisS01Alias) es
exactamente lo que se busca: FOB, peso neto, peso bruto y % de participacion
por pais de destino, a nivel de partida SUNAT (10 digitos), desde 1993.

Lo que se probo:
  - El formulario es un POST simple: ano_prese, tipo_regimen (01=import,
    02=export), part_nandi (10 digitos), accion=consultarResumenPPais.
  - Requiere sesion: sin GET previo al POST devuelve una pagina de error.
  - Con sesion, el POST resuelve bien la DESCRIPCION (0901.11.00.00 CAFE SIN
    TOSTAR, SIN DESCAFEINAR) pero el cuerpo de la tabla sale como
    "No se encontraron registros".
  - Se probo con 2 productos distintos, 3 anos distintos y ambos regimenes
    (incluidas importaciones de cafe en 2015, que existen con gusto). Todo
    vacio. No es un problema de parametros.

Por que se conserva: si SUNAT repuebla la tabla, esto funciona. El scraper esta
completo y probado salvo por la respuesta vacia. No lo actives sin verificar.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import pandas as pd
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "http://www.aduanet.gob.pe/cl-ad-itestadispartida/resumenPPaisS01Alias"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}

REGIMEN_IMPORTACION = "01"
REGIMEN_EXPORTACION = "02"


@dataclass
class SunatResult:
    year: int
    regimen: str
    nandina: str
    description: str
    rows: pd.DataFrame  # vacio si la consulta no trajo registros


def _strip_accents(text: str) -> str:
    """La pagina viene en ISO-8859-1 y el terminal no siempre la maneja."""
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "Á": "A", "É": "E"}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def fetch_acumulado(
    year: int,
    nandina: str,
    regimen: str = REGIMEN_EXPORTACION,
    session: requests.Session | None = None,
) -> SunatResult:
    """Consulta el acumulado anual de SUNAT para una partida NANDINA de 10 digitos.

    Devuelve un DataFrame vacio si SUNAT responde "No se encontraron registros",
    que es el comportamiento actual (2026-09-30).
    """
    if len(nandina) != 10 or not nandina.isdigit():
        raise ValueError(f"Partida NANDINA invalida: {nandina!r}. Se esperan 10 digitos.")

    session = session or requests.Session()
    # El POST sin sesion previa falla: la app espera que se cargue el formulario.
    session.get(BASE_URL, headers=HEADERS, timeout=60)

    response = session.post(
        BASE_URL,
        data={
            "ano_prese": str(year),
            "tipo_regimen": regimen,
            "part_nandi": nandina,
            "accion": "consultarResumenPPais",
        },
        headers={**HEADERS, "Referer": BASE_URL},
        timeout=60,
    )
    response.raise_for_status()
    response.encoding = "iso-8859-1"
    soup = BeautifulSoup(response.text, "html.parser")
    body = _strip_accents(soup.get_text(" ", strip=True))

    description = ""
    match = re.search(r"Subpartida Nacional\s*:?\s*([\d.]+)\s+(.+?)\s+Pa", body)
    if match:
        description = match.group(2).strip()

    if "No se encontraron registros" in body:
        log.warning(
            "SUNAT devolvio 'sin registros' para %s %s. Backend probablemente vacio.",
            nandina, year,
        )
        return SunatResult(year, regimen, nandina, description, pd.DataFrame())

    return SunatResult(year, regimen, nandina, description, _parse_table(soup))


def _parse_table(soup: BeautifulSoup) -> pd.DataFrame:
    """Extrae la tabla de resultados (pais, FOB, peso neto, peso bruto, %)."""
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not any("fob" in h for h in headers):
            continue

        records = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) >= 4 and cells[0] not in ("", "Destino"):
                records.append(cells[:5])

        if not records:
            continue
        frame = pd.DataFrame(records, columns=["pais", "fob_usd", "peso_neto_kg", "peso_bruto_kg", "pct_fob"][: len(records[0])])
        for column in frame.columns[1:]:
            frame[column] = pd.to_numeric(
                frame[column].astype(str).str.replace(r"[^\d.,-]", "", regex=True).str.replace(",", "", regex=False),
                errors="coerce",
            )
        return frame
    return pd.DataFrame()


def fetch_series(nandina: str, years: list[int], regimen: str = REGIMEN_EXPORTACION) -> pd.DataFrame:
    """Serie temporal de la partida, uniendo los resultados por anio."""
    session = requests.Session()
    frames = []
    for year in years:
        result = fetch_acumulado(year, nandina, regimen, session)
        if not result.rows.empty:
            result.rows["year"] = year
            result.rows["nandina"] = nandina
            result.rows["regimen"] = regimen
            frames.append(result.rows)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
