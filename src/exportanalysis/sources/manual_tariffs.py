"""Aranceles de importacion: lo que el mercado destino le cobra a tu producto.

CONTEXTO HONESTO
================
No existe una API gratuita, estable y sin registro que te devuelva el arancel
aplicado a un HS-6 para un par (pais destino, pais de origen). Se verificaron
las opciones el 2026-09-30 y asi quedaron:

  SUNAT (aduanet, "Acumulado anual subpartida/pais")
      Responde 200 y resuelve la descripcion del producto, pero devuelve
      "No se encontraron registros" para TODO, incluidas importaciones de cafe
      en 2015 que si existen. Backend vacio. NO usable.
      (El formulario es un POST con sesion previa; si SUNAT lo arregla, el
      scraper esta en `sunat.py` como referencia.)

  WITS / World Bank  (arancel bilateral a nivel HS-6, el mas completo)
      El endpoint documentado responde 400/403/405 segun la variante de URL.
      Se dejo `wits.py` con el contrato correcto segun la documentacion oficial
      (SDMX, reporter en M49 numerico) pero NO esta verificado contra
      respuesta 200. Activalo solo si lo validas a mano.

  WTO API            Requiere registro y subscription key. Gratis, pero signup.

  UNCTAD TRAINS      Es la fuente real de WITS. No es gratuita.

  ITC Trade Map / Market Access Map
      GRATIS e incluye el arancel, junto con la data de comercio. Es
      practicamente con certeza "la pagina gratis que te daba data y el
      arancel". Peru es pais en desarrollo, asi que da acceso completo sin
      pagar. Limitacion: no hay API publica (el propio ITC lo dice en su FAQ),
      pero exporta a Excel. Ese Excel se pega aqui.

DECISION DE DISENO
==================
Por eso este modulo es un archivo CSV editable y no un scraper. Es la opcion
correcta, no un atajo: el arancel es un dato de politica comercial que cambia
por acuerdo comercial y por medida de antidumping, y alguien tiene que
firmar que el numero es correcto. Ademas el arancel casi nunca es el factor
decisivo frente al flete, el cumplimiento y el precio de venta.

USO
===
1. Registrate gratis en https://marketanalysis.intracen.org/ (o trademarks.org)
2. Market Access Map -> pais destino -> tu HS-6 -> origina Peru -> exportar
3. Pegar la fila en data/raw/tariffs/tariffs.csv
4. Si el arancel real es 0% por TLC, poner 0.0. Si no se conoce, dejar vacio:
   el modelo lo marca como supuesto, no como dato.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..config import DATA_DIR, country_name

log = logging.getLogger(__name__)

TARIFF_FILE = DATA_DIR / "raw" / "tariffs" / "tariffs.csv"

COLUMNS = [
    "hs6",             # codigo HS-6
    "destination",     # M49 del pais que IMPORTA
    "origin",          # M49 del pais que EXPORTA (604 = Peru)
    "duty_type",       # MFN | PREF | AHS  (arancel aplicado, preferencial, MFN)
    "duty_pct",        # arancel ad valorem en %, sobre el valor CIF
    "year",            # anio del dato
    "source",          # de donde salio: Market Access Map, WTO, correo del broker...
    "notes",
]

TEMPLATE_ROWS = [
    {
        "hs6": "090111",
        "destination": 842,
        "origin": 604,
        "duty_type": "PREF",
        "duty_pct": 0.0,
        "year": 2025,
        "source": "Market Access Map (revisar: USA aplica TLC con Peru?)",
        "notes": "Ejemplo de plantilla. Verificar antes de usar en el modelo.",
    },
    {
        "hs6": "090111",
        "destination": 276,
        "origin": 604,
        "duty_type": "PREF",
        "duty_pct": 0.0,
        "year": 2025,
        "source": "Acuerdo UE-Peru",
        "notes": "",
    },
    {
        "hs6": "090111",
        "destination": 392,
        "origin": 604,
        "duty_type": "MFN",
        "duty_pct": None,
        "year": 2025,
        "source": "Market Access Map",
        "notes": "Dejar vacio si no se conoce: el modelo lo tratara como supuesto.",
    },
]


def ensure_template() -> Path:
    """Crea el CSV con filas de ejemplo si no existe."""
    if TARIFF_FILE.exists():
        return TARIFF_FILE
    TARIFF_FILE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(TEMPLATE_ROWS, columns=COLUMNS).to_csv(TARIFF_FILE, index=False)
    log.info("Plantilla de aranceles creada en %s", TARIFF_FILE)
    return TARIFF_FILE


def load_tariffs(hs6: str | None = None) -> pd.DataFrame:
    """Aranceles cargados a mano, opcionalmente filtrados por producto."""
    if not TARIFF_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)

    frame = pd.read_csv(TARIFF_FILE, dtype={"hs6": str, "destination": "Int64", "origin": "Int64"})
    frame["hs6"] = frame["hs6"].str.zfill(6)
    if hs6:
        frame = frame[frame["hs6"] == str(hs6).zfill(6)]

    frame["duty_pct"] = pd.to_numeric(frame["duty_pct"], errors="coerce")
    frame["destination_name"] = frame["destination"].map(country_name)
    frame["is_estimated"] = frame["duty_pct"].isna()
    return frame.reset_index(drop=True)


def tariff_for(hs6: str, destination: int, origin: int = 604) -> float | None:
    """Arancel mas reciente y aplicable para un par (producto, destino).

    Devuelve None si no hay dato. La cadena de decision es:
      1. PREFERENCIAL  -> si hay acuerdo comercial, manda (suele ser 0%)
      2. AHS           -> arancel efectivamente aplicado (promedio real)
      3. MFN           -> linea nacional, el peor caso
    Se toma el anio mas reciente disponible de cada tipo.
    """
    frame = load_tariffs(hs6)
    frame = frame[(frame["destination"] == destination) & (frame["origin"] == origin)]
    if frame.empty:
        return None

    for duty_type in ("PREF", "AHS", "MFN"):
        subset = frame[(frame["duty_type"] == duty_type) & frame["duty_pct"].notna()]
        if not subset.empty:
            latest = subset.loc[subset["year"].idxmax()]
            return float(latest["duty_pct"])
    return None


def tariff_table(hs6: str, destinations: list[int], origin: int = 604) -> pd.DataFrame:
    """Tabla arancel para varios destinos, lista para el reporte."""
    rows = [
        {
            "destination_code": code,
            "destination_name": country_name(code),
            "duty_pct": tariff_for(hs6, code, origin),
        }
        for code in destinations
    ]
    frame = pd.DataFrame(rows)
    frame["is_estimated"] = frame["duty_pct"].isna()
    return frame
