"""Asistente de arancel: te dice exactamente que buscar en ITC Trade Map.

POR QUE ESTO NO ES UN SCRAPER
=============================
Trade Map es la fuente gratuita correcta para el arancel (Peru es pais en
desarrollo, asi que tiene acceso completo), pero NO tiene API. No es una
limitacion que se pueda sortear con ingenieria:

  - El propio ITC lo dice en su FAQ: solo dan acceso a una API "in very
    specific circumstances". La herramienta "esta disenada para responder
    consultas puntuales, no para descargar datasets".
  - Es una aplicacion web de ASP.NET: los datos entran por XHR con un token de
    sesion. Se comprobo el 2026-09-30 que hasta las URLs profundas devuelven
    siempre el mismo shell de "Trade Map beta is loading", asi que no se puede
    generar un link que llegue direto a la celda del arancel.
  - Los endpoints internos cambian sin aviso y no hay contrato que los proteja.

Alternativa historica: UN Comtrade publica el endpoint `data/v1/getTariffline`
(arancel line a line), pero requiere `subscription-key`. El proyecto corre
offline, asi que no se usa: el arancel entra a mano por el CSV.

QUE HACE
========
Reemplaza "buscar el arancel del cafe peruano para Estados Unidos" por una
lista concreta de consultas. Para cada destino real de tu producto te dice el
codigo HS-6, la partida NANDINA, el nombre del pais, que palabras escribir, y
que valor hay ahora en el CSV. Con `--fill` te pregunta los numeros y escribe
el CSV solo, sin que tengas que editarlo a mano ni acordarte del formato.

USO
====
    python scripts/tariff_helper.py                      # checklist de cafe_verde
    python scripts/tariff_helper.py --product cacao_en_grano
    python scripts/tariff_helper.py --csv                # bloque para pegar
    python scripts/tariff_helper.py --fill               # pregunta y escribe
    python scripts/tariff_helper.py --fill --keep         # no pisa lo existente

Los destinos que lista son los reales del ultimo anio con data (los mismos que
usa el reporte), no una lista inventada: el arancel que importa es el del pais
que te compra.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from exportanalysis.config import country_name, get_product, load_catalog  # noqa: E402
from exportanalysis.pipeline import excel_analysis, market  # noqa: E402
from exportanalysis.sources.manual_tariffs import COLUMNS, TARIFF_FILE, tariff_for  # noqa: E402

TRADEMAP_URL = "https://www.trademap.org/"

DUTY_TYPES = ("PREF", "AHS", "MFN")
DUTY_HELP = (
    "PREF = preferencial por acuerdo comercial (suele ser 0%) | "
    "AHS = arancel efectivamente aplicado | MFN = linea nacional, el peor caso"
)


def _product(slug: str | None):
    catalog = load_catalog()
    if slug:
        return get_product(slug)
    for candidate in catalog.products:
        if candidate.hs6 == "090111":
            return candidate
    return catalog.products[0]


def _destinations(hs6: str, origin: int, configured: list[int]) -> tuple[list[int], str]:
    """Destinos reales del ultimo anio con data; si no hay data, los del config."""
    try:
        trade = excel_analysis.peru_exports_trade(hs6)
        frame = market.destination_breakdown(trade)
        if not frame.empty:
            return frame["partner_code"].head(6).tolist(), "destinos reales (Trade Map Excel)"
    except Exception as exc:  # noqa: BLE001 - aca un archivo faltante no debe tumbar la ayuda
        print(f"  aviso: no se pudo leer el Excel de Trade Map ({exc}); uso los competidores del config.", file=sys.stderr)
    return list(configured), "competidores del config (sin data de destinos)"


def _existing(hs6: str, destination: int, origin: int) -> str:
    """Valor actual en el CSV, marcando los que son plantilla y no dato verificado.

    Importa mas de lo que parece: las filas de ejemplo se escriben con 0.0, y si
    el reporte las trata como "dato publicado" estariamos afirmando un arancel
    de 0% que nadie verifico. Por eso el placeholder se dice explicitamente.
    """
    frame = pd.read_csv(TARIFF_FILE, dtype=str).fillna("") if TARIFF_FILE.exists() else pd.DataFrame(columns=COLUMNS)
    if frame.empty:
        return "sin dato"
    rows = frame[
        (frame["hs6"].str.zfill(6) == hs6)
        & (frame["destination"].astype(str) == str(destination))
        & (frame["origin"].astype(str) == str(origin))
    ]
    rows = rows[rows["duty_pct"].str.strip() != ""]
    if rows.empty:
        return "sin dato"
    row = rows.sort_values("year").iloc[-1]
    value = row["duty_pct"]
    is_placeholder = "plantilla" in (row["notes"] + row["source"]).lower()
    if is_placeholder:
        return f"{value} %  <-- PLANTILLA, sin verificar"
    return f"{value} %  ({row['duty_type']}, {row['year']})"


def _checklist(hs6: str, nandina: str | None, destinations: list[int], origin: int, year: int, source: str) -> None:
    print()
    print("=" * 78)
    print(f"  ARANCEL  |  HS-6 {hs6}" + (f"  |  NANDINA {nandina}" if nandina else ""))
    print(f"  Pais de origen: {country_name(origin)} ({origin})")
    print(f"  Anio a consultar: {year}   |  Fuente: {source}")
    print("=" * 78)
    print()
    print(f"  Abrir: {TRADEMAP_URL}")
    print("  En el buscador de productos escribir el codigo HS-6; en el menu de")
    print("  pais, elegir el destino. Leer el arancel de 'Applied duty (AHS)' y")
    print("  tambien el preferencial si hay acuerdo comercial.")
    print(f"  Como se elige el tipo: {DUTY_HELP}")
    print()

    for code in destinations:
        name = country_name(code)
        print(f"  [{code}] {name}")
        print(f"        buscar:  HS {hs6}  ->  {name}  ->  applied duty / arancel")
        print(f"        actual:  {_existing(hs6, code, origin)} en {TARIFF_FILE.name}")
    print()


def _csv_lines(hs6: str, destinations: list[int], origin: int, year: int) -> str:
    # Ojo: la columna `hs6` es el codigo de 6 digitos, NO la partida NANDINA de
    # 10. El cargador (load_tariffs) compara contra el HS-6 del producto, asi que
    # escribir 0901110000 ahi deja la fila sin coincidir nunca.
    lines = [",".join(COLUMNS)]
    for dest in destinations:
        lines.append(f"{hs6},{dest},{origin},MFN,,{year},ITC Trade Map,")
    return "\n".join(lines)


def _fill(hs6: str, nandina: str | None, destinations: list[int], origin: int, year: int, keep: bool) -> None:
    """Pregunta el arancel de cada destino y escribe el CSV."""
    frame = pd.read_csv(TARIFF_FILE, dtype=str) if TARIFF_FILE.exists() else pd.DataFrame(columns=COLUMNS)
    frame = frame.fillna("")

    print()
    print("  Escribe el arancel en PORCENTAJE (6.0 = 6%). Vacio = no lo se, y el")
    print("  modelo lo va a marcar como supuesto. Ctrl+C para salir sin escribir.")
    print()

    added = 0
    for dest in destinations:
        name = country_name(dest)
        current = tariff_for(hs6, dest, origin)
        default = "" if current is None else f"{current:g}"
        try:
            raw = input(f"  [{dest}] {name} (actual: {default or 'sin dato'}) %: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelado; no se escribio nada.")
            return

        if keep and raw == "" and current is not None:
            continue

        duty_type = "PREF" if raw != "" and float(raw) == 0.0 else "MFN"
        row = {
            "hs6": hs6,
            "destination": dest,
            "origin": origin,
            "duty_type": duty_type,
            "duty_pct": raw,
            "year": year,
            "source": "ITC Trade Map",
            "notes": "",
        }
        mask = (frame["hs6"].str.zfill(6) == hs6) & (frame["destination"] == str(dest)) & (frame["origin"] == str(origin))
        frame = frame[~mask]
        frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
        added += 1

    TARIFF_FILE.parent.mkdir(parents=True, exist_ok=True)
    frame[COLUMNS].to_csv(TARIFF_FILE, index=False)
    print(f"\n  {added} fila(s) escritas en {TARIFF_FILE}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Asistente de arancel para ITC Trade Map (sin scraping: no hay API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--product", help="slug del producto (por defecto: cafe_verde)")
    parser.add_argument("--csv", action="store_true", help="imprime un bloque CSV para pegar")
    parser.add_argument("--fill", action="store_true", help="pregunta los aranceles y escribe el CSV")
    parser.add_argument("--keep", action="store_true", help="con --fill, no borra lo que ya tiene dato")
    parser.add_argument("--year", type=int, default=None, help=f"anio del dato (por defecto {pd.Timestamp.now().year - 1})")
    args = parser.parse_args()

    product = _product(args.product)
    catalog = load_catalog()
    origin = catalog.defaults.reporter
    year = args.year or (pd.Timestamp.now().year - 1)
    destinations, source = _destinations(product.hs6, origin, product.competitors)

    if not destinations:
        print("  No hay destinos: el producto no tiene data de comercio ni competidores en el config.")
        return 1

    if args.csv:
        print(_csv_lines(product.hs6, destinations, origin, year))
        return 0

    _checklist(product.hs6, product.nandina, destinations, origin, year, source)

    if args.fill:
        _fill(product.hs6, product.nandina, destinations, origin, year, args.keep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
