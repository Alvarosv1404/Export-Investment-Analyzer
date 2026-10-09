"""Adaptador de WITS / World Bank para arancel bilateral. NO VERIFICADO.

ESTADO: sin validar. Ver `manual_tariffs.py` para el detalle de por que el
arancel se carga a mano por defecto.

Lo que se verifico el 2026-09-30:
  reporter con codigo ISO3 ("usa")  -> HTTP 400 "Invalid Reporter Code"
  reporter con M49 numerico (842)    -> el parametro se acepta
  partner con M49 (604)             -> HTTP 400 "Invalid Partner Code"
  base /API/V1/WITS/...             -> HTTP 405 en todos los metodos GET
  base /API/V1/SDMX/V21/...         -> 400 / 403 / 404 segun la variante

Conclusion: el servicio esta restringiendo acceso automatizado. Este modulo
deja el contrato documentado y una funcion de diagnostico para que, si WITS
vuelve a estar disponible o si prefieres la API de WTO (que pide key
gratuita), solo tengas que rellenar el parser.

NO LO USES EN EL MODELO sin verificar contra la UI de
https://wits.worldbank.org/ primero.
"""

from __future__ import annotations

import logging

import requests

from ..cache import build_session
from .manual_tariffs import tariff_for

log = logging.getLogger(__name__)

WITS_SDMX = "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN"

# WITS usa M49 numerico para el reporter (verificado: 842 = USA es aceptado).
COUNTRY_CODES = {
    "peru": 604, "estados unidos": 842, "alemania": 276, "espana": 724,
    "italia": 380, "francia": 250, "paises bajos": 528, "reino unido": 826,
    "japon": 392, "china": 156, "canada": 124, "belgica": 56, "suecia": 752,
    "rusia": 643, "chile": 152, "argentina": 32, "australia": 36,
    "colombia": 170, "brasil": 76, "ecuador": 218, "costa rica": 188,
    "mexico": 484, "guatemala": 320, "honduras": 340, "nicaragua": 558,
}


def build_url(reporter: int, partner: int, product: str, year: int) -> str:
    """URL documentada por WITS para arancel bilateral a nivel HS-6."""
    return (
        f"{WITS_SDMX}/reporter/{reporter}/partner/{partner}"
        f"/product/{product}/year/{year}/datatype/reported?format=JSON"
    )


def diagnose(product: str = "090111", reporter: int = 842, partner: int = 604) -> str:
    """Prueba la API y devuelve un diagnostico legible. Util para debug."""
    session = build_session()
    url = build_url(reporter, partner, product, 2023)
    try:
        response = session.get(url, timeout=60)
    except requests.RequestException as exc:
        return f"Error de red contra WITS: {exc}"
    if response.ok:
        return f"WITS responde {response.status_code}. Body inicial: {response.text[:300]}"
    return (
        f"WITS responde {response.status_code} a {url}\n"
        f"Body: {response.text[:500]}\n"
        "Usar manual_tariffs.py (Market Access Map) mientras tanto."
    )


def fetch_tariff(reporter: int, partner: int, product: str, year: int) -> float | None:
    """Arancel simple promedio en %, o None si WITS no responde.

    Cuando se implemente el parser de SDMX, las medidas de interes son
    OBS_Value (simple average) y el atributo TARIFFTYPE (MFN / PREF).
    """
    session = build_session()
    url = build_url(reporter, partner, product, year)
    try:
        response = session.get(url, timeout=60)
    except requests.RequestException as exc:
        log.warning("WITS no accesible: %s", exc)
        return None
    if not response.ok:
        log.warning("WITS HTTP %s para %s", response.status_code, url)
        return None

    # Parser SDMX pendiente: la API devuelve XML por defecto y JSON solo con
    # ?format=JSON, con una estructura anidada que hay que mapear a mano.
    log.warning("Parser de WITS no implementado. Usar manual_tariffs.")
    return None


def tariff_with_fallback(
    hs6: str, destination: int, origin: int = 604, year: int = 2023
) -> float | None:
    """Intenta WITS y, si falla, cae al archivo manual."""
    value = fetch_tariff(destination, origin, hs6, year)
    if value is not None:
        return value
    return tariff_for(hs6, destination, origin)
