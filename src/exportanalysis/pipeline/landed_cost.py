"""Costo puesto en destino (landed cost) y precio de venta al importador.

Este modulo es donde el arancel entra al calculo. Recalca por que el arancel es
menos importante de lo que parece y por que igual hay que modelarlo:

  CIF     = FOB + flete + seguro
  tasa    = duty_pct / 100          <- duty_pct va en PORCENTAJE
  Arancel = CIF * tasa
  Precio en planta del importador = CIF + Arancel

Un arancel de 10% sobre un producto cuyo flete es 5% del FOB mueve el precio
poco. Uno de 60% lo destruye. Por eso el escenario se corre con arancel real y
no con el peor caso.

UNIDAD DE duty_pct
==================
`duty_pct` se expresa en PORCENTAJE (6.0 significa 6%), que es como viene en
`data/raw/tariffs/tariffs.csv` y como lo muestra el reporte. La fraccion
(0.06) es interna de la funcion. Confundir las dos produce un arancel de 600%
y un error de mil veces en el costo en destino, asi que la conversion se hace
en un solo punto: `_duty_rate()`.
"""

from __future__ import annotations

import pandas as pd

from ..sources.manual_tariffs import tariff_for


def _duty_rate(duty_pct: float | None) -> float:
    """Convierte arancel en porcentaje a fraccion. 6.0 -> 0.06."""
    return (duty_pct or 0.0) / 100.0


def landed_cost(
    fob_usd_per_kg: float,
    *,
    freight_pct_fob: float = 0.05,
    insurance_pct_fob: float = 0.005,
    duty_pct: float | None = 0.0,
) -> dict:
    """Descompone el costo de poner 1 kg en planta del importador.

    Los porcentajes son fracciones sobre el FOB, EXCEPTO `duty_pct`, que va en
    porcentaje porque es como se carga en el CSV. El arancel se aplica sobre el
    CIF (base imponible de aduanas), no sobre el FOB.
    """
    freight = fob_usd_per_kg * freight_pct_fob
    insurance = fob_usd_per_kg * insurance_pct_fob
    cif = fob_usd_per_kg + freight + insurance
    duty_rate = _duty_rate(duty_pct)
    duty = cif * duty_rate
    duty_free = cif + duty
    return {
        "fob_usd_per_kg": round(fob_usd_per_kg, 4),
        "freight_usd_per_kg": round(freight, 4),
        "insurance_usd_per_kg": round(insurance, 4),
        "cif_usd_per_kg": round(cif, 4),
        "duty_pct": duty_pct,
        "duty_rate": round(duty_rate, 6),
        "duty_usd_per_kg": round(duty, 4),
        "landed_usd_per_kg": round(duty_free, 4),
        # Quanto de la factura del importador es arancel. Si esto es pequeno,
        # el arancel no va a decidir la inversion.
        "duty_share_of_landed": round(duty / duty_free, 4) if duty_free else 0.0,
    }


def price_positioning(
    fob_usd_per_kg: float,
    *,
    freight_pct_fob: float = 0.05,
    duty_pct: float | None = 0.0,
    target_margin: float = 0.15,
) -> dict:
    """Precio al que tendria que vender el exportador para dado margen del importador.

    Se invierte la ecuacion del landed cost: si el importador necesita un
    margen sobre su precio de venta, ese precio de venta determina el
    landed cost maximo, y de ahi el FOB maximo que se puede cobrar.
    """
    freight = fob_usd_per_kg * freight_pct_fob
    insurance = fob_usd_per_kg * 0.005
    cif = fob_usd_per_kg + freight + insurance
    duty_rate = _duty_rate(duty_pct)

    # landed = fob*(1+fl+seg)*(1+duty);  precio_venta = landed / (1 - margen)
    landed = cif * (1 + duty_rate)
    retail = landed / (1 - target_margin)
    duty_effective = landed - cif

    return {
        "landed_usd_per_kg": round(landed, 4),
        "importer_price_usd_per_kg": round(retail, 4),
        "duty_pct": duty_pct,
        "duty_effective_usd_per_kg": round(duty_effective, 4),
        "target_margin": target_margin,
        "note": (
            "El margen del importador se aplica sobre su precio de venta, no sobre "
            "el costo. El resto de la cadena (distribuidor, minorista) queda fuera."
        ),
    }


def tariff_sensitivity(
    fob_usd_per_kg: float, hs6: str, destination: int, origin: int = 604
) -> pd.DataFrame:
    """Como cambia el costo puesto en destino ante distintos aranceles.

    Sirve para responder la pregunta clasica de inversion: "si me suben el
    arancel, muero?". Se corre sobre la tarifa real cargada y sobre un rango
    alrededor, porque la tarifa real es un dato que puede estar desactualizado.
    """
    real = tariff_for(hs6, destination, origin)
    # anchor_rate es fraccion porque los deltas de este barrido son fracciones.
    anchor_rate = _duty_rate(real)

    rows = []
    for delta in (-0.10, -0.05, 0.0, 0.05, 0.10, 0.25):
        rate = max(0.0, anchor_rate + delta)
        detail = landed_cost(fob_usd_per_kg, duty_pct=rate * 100)
        rows.append(
            {
                "duty_pct": round(rate * 100, 2),
                "is_real_tariff": real is not None and abs(rate - anchor_rate) < 1e-9,
                "landed_usd_per_kg": detail["landed_usd_per_kg"],
                "duty_share_of_landed": detail["duty_share_of_landed"],
            }
        )
    return pd.DataFrame(rows)
