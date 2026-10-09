"""Analisis desde Excel Trade Map organizados por HS6."""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from ..config import DATA_DIR


def _find(hs6: str, pattern: str) -> Path:
    for p in DATA_DIR.rglob(pattern.format(hs6=hs6)):
        if "_cache" not in str(p):
            return p
    raise FileNotFoundError(pattern.format(hs6=hs6))


def peru_exports_ts(hs6: str) -> pd.DataFrame:
    """Exportaciones peruanas por socio (time series con valor en USD Thousand)."""
    p = _find(hs6, "perus-exports-to-world-by-importer_{hs6}.xlsx")
    df = pd.read_excel(p)
    df = df[df["partnerLabel"] != "World"].copy()
    year_cols = [c for c in df.columns if str(c).split(" ")[0].isdigit()]
    df_m = pd.melt(df, id_vars=["partnerCd", "partnerLabel", "productCd", "productLabel"],
                   value_vars=year_cols, var_name="year", value_name="fob_usd_thousand")
    df_m["year"] = df_m["year"].str.split(" ", n=1).str[0].astype(int)
    df_m["fob_usd"] = df_m["fob_usd_thousand"] * 1000.0
    return df_m[["year", "partnerCd", "partnerLabel", "fob_usd"]].dropna()


def world_exports(hs6: str) -> pd.DataFrame:
    p = _find(hs6, "exporting-economies_{hs6}.xlsx")
    df = pd.read_excel(p)
    year_cols = [c for c in df.columns if str(c).split(" ")[0].isdigit()]
    df_m = pd.melt(df, id_vars=["reporterCd", "reporterLabel", "partnerCd", "partnerLabel"],
                   value_vars=year_cols, var_name="year", value_name="fob_usd_thousand")
    df_m["year"] = df_m["year"].str.split(" ", n=1).str[0].astype(int)
    df_m["fob_usd"] = df_m["fob_usd_thousand"] * 1000.0
    return df_m


def world_imports(hs6: str) -> pd.DataFrame:
    p = _find(hs6, "importing-economies_{hs6}.xlsx")
    df = pd.read_excel(p)
    year_cols = [c for c in df.columns if str(c).split(" ")[0].isdigit()]
    df_m = pd.melt(df, id_vars=["reporterCd", "reporterLabel", "partnerCd", "partnerLabel"],
                   value_vars=year_cols, var_name="year", value_name="cif_usd_thousand")
    df_m["year"] = df_m["year"].str.split(" ", n=1).str[0].astype(int)
    df_m["cif_usd"] = df_m["cif_usd_thousand"] * 1000.0
    return df_m
