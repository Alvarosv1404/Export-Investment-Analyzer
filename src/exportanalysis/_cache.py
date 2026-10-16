"""Caché en proceso de las lecturas de Excel.

Por que existe
==============
Leer un .xlsx con pandas significa descomprimir el zip y parsear su XML: cuesta
entre decenas y cientos de milisegundos por archivo. Ademas, un solo analisis
lee el MISMO archivo varias veces (world_exports se pide en share_trends, en
headroom, en resolve_competitors y en world_share_by_year), y cada request HTTP
repetia todo ese trabajo aunque la data en data/ no hubiera cambiado. Este
modulo cachea el DataFrame ya parseado, en memoria y solo por la vida del
proceso, que es justo lo que necesita una app que sirve reportes sobre data
estatica.

Invalidacion
============
La clave incluye el mtime del archivo. Si alguien reemplaza un Excel en data/,
el mtime cambia, la clave ya no coincide y se vuelve a leer. No hay que
reiniciar el servidor ni limpiar nada a mano. clear_cache() existe para tests y
para forzar una recarga en caliente.

Seguridad (subprocesos)
=======================
FastAPI corre los endpoints `def` en un pool de hilos, asi que el acceso al
cache esta protegido con un lock. El DataFrame cacheado se COMPARTE: quien lo
consuma no debe mutarlo en el sitio, sino derivar uno nuevo (copiar, melt,
seleccionar columnas). Todas las funciones lectoras de excel_analysis ya derivan
un frame nuevo; la unica que mutaba en el sitio (peru_exports_indicators_2025)
copia antes de tocar nada.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pandas as pd

_lock = threading.Lock()
_cache: dict[tuple, pd.DataFrame] = {}


def read_excel_cached(path, sheet_name=0, **kwargs) -> pd.DataFrame:
    """Lee un Excel y cachea el DataFrame por (ruta, hoja, mtime)."""
    p = Path(path)
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = None
    key = (str(p), str(sheet_name), mtime)
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    df = pd.read_excel(p, sheet_name=sheet_name, **kwargs)
    with _lock:
        _cache[key] = df
    return df


def clear_cache() -> None:
    """Vacia el cache. Util en tests o para recargar data en caliente."""
    with _lock:
        _cache.clear()


def cache_size() -> int:
    with _lock:
        return len(_cache)
