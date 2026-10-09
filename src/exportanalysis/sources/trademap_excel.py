"""Carga de archivos Excel exportados desde Trade Map.

Formatos esperados:
- exporting-economies_*.xlsx / importing-economies_*: por pais exportador/importador, valor en (USD Thousand) por año
- perus-exports-to-world-by-importer_*.xlsx: exportaciones peruanas por socio, valor en (USD Thousand)
- perus-indicadores-exports-to-world-in-2025-by-importer_*: snapshot 2025 con Value (kUSD), Quantity, Unit Value
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from ..config import DATA_DIR


def _find(hs6: str, pattern: str) -> Path:
    for p in DATA_DIR.rglob(pattern.format(hs6=hs6)):
        if "_cache" not in str(p):
            return p
    raise FileNotFoundError(pattern.format(hs6=hs6))


def load_peru_by_partner(hs6: str) -> pd.DataFrame:
    p = _find(hs6, "perus-exports-to-world-by-importer_{hs6}.xlsx")
    df = pd.read_excel(p)
    df = df[df["partnerLabel"] != "World"]
    df["reporterCd"] = df["reporterCd"].astype(str).str.zfill(3)
    df["partnerCd"] = df["partnerCd"].astype(str).str.zfill(3)
    return df
def load_indicadores_2025(hs6: str) -> pd.DataFrame:
    p = _find(hs6, "perus-indicadores-exports-to-world-in-2025-by-importer_{hs6}.xlsx")
    df = pd.read_excel(p)
    df = df[df["partnerLabel"] != "World"]
    df["partnerCd"] = df["partnerCd"].astype(str).str.zfill(3)
    return df
