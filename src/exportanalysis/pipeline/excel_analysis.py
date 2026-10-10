"""Analisis desde Excel Trade Map organizados por HS6.

Este modulo es la unica puerta de entrada a los datos de mercado. Lee los
cuatro Excel que Trade Map exporta por producto, sin red, sin claves y sin
cache: `data/<hs6> <nombre>/`.

Nombres de archivo esperados (exactos):
    1. exporting-economies_<hs6>.xlsx                 exportadores mundiales
    2. importing-economies_<hs6>.xlsx                 importadores mundiales
    3. perus-exports-to-world-by-importer_<hs6>.xlsx  serie historica por destino (USD Thousand)
    4. perus-exports-to-world-in-2025-by-importer_<hs6>.xlsx  snapshot 2025 (Value kUSD, Quantity, Unit Value)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..config import DATA_DIR


def _find(hs6: str, pattern: str) -> Path:
    """Busca un Excel por HS6 en data/, ignorando la carpeta de cache."""
    for p in DATA_DIR.rglob(pattern.format(hs6=hs6)):
        if "_cache" not in str(p):
            return p
    raise FileNotFoundError(pattern.format(hs6=hs6))


def _year_columns(df: pd.DataFrame) -> list[str]:
    """Columnas de anio ("2024 (USD Thousand)") de un Excel de Trade Map."""
    return [c for c in df.columns if str(c).split(" ")[0].isdigit()]


def peru_exports_ts(hs6: str) -> pd.DataFrame:
    """Exportaciones peruanas por socio (serie historica, valor en USD).

    Excluye la fila de total "World": las series por destino no la necesitan y
    sumarla duplicaria el total. Para el total usa `peru_exports_trade`.
    """
    p = _find(hs6, "perus-exports-to-world-by-importer_{hs6}.xlsx")
    df = pd.read_excel(p)
    df = df[df["partnerLabel"] != "World"].copy()
    year_cols = _year_columns(df)
    df_m = pd.melt(
        df,
        id_vars=["partnerCd", "partnerLabel", "productCd", "productLabel"],
        value_vars=year_cols,
        var_name="year",
        value_name="fob_usd_thousand",
    )
    df_m["year"] = df_m["year"].astype(str).str.split(" ", n=1).str[0].astype(int)
    df_m["fob_usd"] = pd.to_numeric(df_m["fob_usd_thousand"], errors="coerce") * 1000.0
    return df_m[["year", "partnerCd", "partnerLabel", "fob_usd"]].dropna(subset=["fob_usd"])


def peru_exports_trade(hs6: str) -> pd.DataFrame:
    """Exportaciones peruanas por destino en formato compatible con `market.py`.

    Incluye la fila de total "World" (partner 0) porque los totales anuales y la
    concentracion se calculan sobre ella. El volumen (`net_weight_kg`) solo
    existe en el snapshot 2025 (Quantity, Tons); los demas anios quedan sin
    volumen, que es un hueco real de la fuente, no un cero.
    """
    p = _find(hs6, "perus-exports-to-world-by-importer_{hs6}.xlsx")
    df = pd.read_excel(p)
    year_cols = _year_columns(df)

    df = df[["partnerCd", "partnerLabel", *year_cols]].copy()
    df["partner_code"] = pd.to_numeric(df["partnerCd"], errors="coerce").astype("Int64")
    df["partner_name"] = df["partnerLabel"]
    df["is_world"] = df["partner_code"] == 0
    df = df.drop(columns=["partnerCd", "partnerLabel"])

    melted = pd.melt(
        df,
        id_vars=["partner_code", "partner_name", "is_world"],
        value_vars=year_cols,
        var_name="year",
        value_name="fob_usd_thousand",
    )
    melted["year"] = melted["year"].astype(str).str.split(" ", n=1).str[0].astype(int)
    melted["fob_usd"] = pd.to_numeric(melted["fob_usd_thousand"], errors="coerce") * 1000.0
    melted["net_weight_kg"] = np.nan

    # Volumen del ultimo anio (2025): el unico Excel que publica cantidad.
    try:
        ind = peru_exports_indicators_2025(hs6, include_world=True)
        qty = {
            int(code): float(kg)
            for code, kg in zip(ind["partner_code"], ind["quantity_kg"], strict=False)
            if pd.notna(kg) and pd.notna(code)
        }
        is_latest = melted["year"] == 2025
        melted.loc[is_latest, "net_weight_kg"] = melted.loc[is_latest, "partner_code"].map(qty)
    except (FileNotFoundError, KeyError, ValueError):
        pass

    return (
        melted[["year", "partner_code", "partner_name", "is_world", "fob_usd", "net_weight_kg"]]
        .sort_values(["year", "fob_usd"], ascending=[True, False])
        .reset_index(drop=True)
    )


def world_exports(hs6: str) -> pd.DataFrame:
    """Exportaciones por pais exportador (partner = World), serie historica."""
    p = _find(hs6, "exporting-economies_{hs6}.xlsx")
    df = pd.read_excel(p)
    year_cols = _year_columns(df)
    df_m = pd.melt(
        df,
        id_vars=["reporterCd", "reporterLabel", "partnerCd", "partnerLabel"],
        value_vars=year_cols,
        var_name="year",
        value_name="fob_usd_thousand",
    )
    df_m["year"] = df_m["year"].astype(str).str.split(" ", n=1).str[0].astype(int)
    df_m["fob_usd"] = pd.to_numeric(df_m["fob_usd_thousand"], errors="coerce") * 1000.0
    return df_m


def world_imports(hs6: str) -> pd.DataFrame:
    """Importaciones por pais importador (partner = World), serie historica."""
    p = _find(hs6, "importing-economies_{hs6}.xlsx")
    df = pd.read_excel(p)
    year_cols = _year_columns(df)
    df_m = pd.melt(
        df,
        id_vars=["reporterCd", "reporterLabel", "partnerCd", "partnerLabel"],
        value_vars=year_cols,
        var_name="year",
        value_name="cif_usd_thousand",
    )
    df_m["year"] = df_m["year"].astype(str).str.split(" ", n=1).str[0].astype(int)
    df_m["cif_usd"] = pd.to_numeric(df_m["cif_usd_thousand"], errors="coerce") * 1000.0
    return df_m


def peru_exports_indicators_2025(hs6: str, *, include_world: bool = False) -> pd.DataFrame:
    """Snapshot 2025 por destino: Value (kUSD), Quantity, Unit Value.

    `quantity_kg` normaliza la cantidad a kilos cuando Trade Map la publica en
    toneladas (Quantity Unit = "Tons"). El precio (`unit_value_usd_per_unit`)
    queda en la unidad original de la fuente.
    """
    p = _find(hs6, "perus-exports-to-world-in-2025-by-importer_{hs6}.xlsx")
    df = pd.read_excel(p)
    if not include_world:
        df = df[df["partnerLabel"] != "World"].copy()
    df["partnerCd"] = df["partnerCd"].astype(str).str.zfill(3)
    df["partner_code"] = pd.to_numeric(df["partnerCd"], errors="coerce").astype("Int64")

    out = df[
        ["partnerCd", "partner_code", "partnerLabel", "Value (kUSD)", "Quantity", "Quantity Unit", "Unit Value"]
    ].copy()
    out["fob_usd_thousand"] = pd.to_numeric(out["Value (kUSD)"], errors="coerce")
    out["quantity"] = pd.to_numeric(out["Quantity"], errors="coerce")
    out["unit_value_usd_per_unit"] = pd.to_numeric(out["Unit Value"], errors="coerce")
    unit = out["Quantity Unit"].astype(str).str.lower()
    out["quantity_kg"] = out["quantity"] * unit.str.contains("ton").map({True: 1000.0, False: 1.0})
    out["fob_usd"] = out["fob_usd_thousand"] * 1000.0
    out["year"] = 2025
    return out


def peru_exports_ts_with_quantity(hs6: str) -> pd.DataFrame:
    """Serie por destino con la cantidad (kg) de 2025 donde exista."""
    ts = peru_exports_ts(hs6).copy()
    ts["partnerCd"] = ts["partnerCd"].astype(str).str.zfill(3)
    try:
        ind = peru_exports_indicators_2025(hs6)
        ind = ind[["partnerCd", "year", "quantity", "quantity_kg", "unit_value_usd_per_unit"]]
        return ts.merge(ind, on=["partnerCd", "year"], how="left")
    except (FileNotFoundError, KeyError):
        return ts


def available_years(hs6: str) -> list[int]:
    """Anios con data en el Excel historico, ordenados y sin depender de la red."""
    df = peru_exports_ts(hs6)
    return sorted(df["year"].dropna().astype(int).unique().tolist())


def _find_nandina_file(nandina: str) -> Path:
    """Busca el Excel de SUNAT (hojas por anio) por partida NANDINA."""
    for p in DATA_DIR.rglob(f"{nandina}.xlsx"):
        if "_cache" not in str(p):
            return p
    raise FileNotFoundError(f"{nandina}.xlsx")


def _column_by(cols: list, *needles: str, exclude: tuple[str, ...] = ()) -> str | None:
    """Primera columna cuyo encabezado contiene todos los needles y ningun exclude."""
    for col in cols:
        text = str(col).lower()
        if all(n in text for n in needles) and not any(e in text for e in exclude):
            return col
    return None


def sunat_exports_by_nandina(nandina: str) -> pd.DataFrame:
    """Exportaciones por destino desde el Excel de SUNAT (una hoja por anio).

    Columnas: year, partner_label, fob_usd, net_weight_kg. Se toma el anio del
    nombre de la hoja (p.ej. "2024"); cualquier hoja con otro nombre se ignora.
    El encabezado real es: Pais de Destino, Valor FOB(dolares), Peso Neto(Kilos),
    Peso Bruto(Kilos), Porcentaje FOB, pero se ubican las columnas por nombre para
    no depender del orden ni del idioma exacto de los acentos.
    """
    path = _find_nandina_file(nandina)
    xls = pd.ExcelFile(path)
    frames = []
    for sheet in xls.sheet_names:
        label = str(sheet).strip()
        if not (len(label) == 4 and label.isdigit()):
            continue
        raw = pd.read_excel(xls, sheet_name=sheet)
        if raw.empty:
            continue
        partner_col = raw.columns[0]
        fob_col = _column_by(list(raw.columns), "fob", exclude=("porcentaje", "%"))
        net_col = _column_by(list(raw.columns), "neto")
        if fob_col is None or net_col is None:
            continue
        frame = pd.DataFrame(
            {
                "year": int(label),
                "partner_label": raw[partner_col].astype(str).str.strip(),
                "fob_usd": pd.to_numeric(raw[fob_col], errors="coerce"),
                "net_weight_kg": pd.to_numeric(raw[net_col], errors="coerce"),
            }
        )
        frames.append(frame.dropna(subset=["fob_usd"]))
    if not frames:
        return pd.DataFrame(columns=["year", "partner_label", "fob_usd", "net_weight_kg"])
    return pd.concat(frames, ignore_index=True)


def sunat_annual_summary(nandina: str) -> pd.DataFrame:
    """Serie anual de SUNAT: FOB, peso neto y precio promedio por kilo.

    `price_usd_per_kg` es la division del FOB entre el peso neto en kilos,
    ponderada por destino (suma de FOB / suma de peso neto). Es el precio real
    por kilo, a diferencia del unit value del snapshot, que no siempre trae la
    cantidad en kilos y puede dar un precio irreal.
    """
    df = sunat_exports_by_nandina(nandina)
    if df.empty:
        return pd.DataFrame(columns=["year", "fob_usd", "net_weight_kg", "price_usd_per_kg"])
    summary = df.groupby("year", as_index=False).agg(
        fob_usd=("fob_usd", "sum"),
        net_weight_kg=("net_weight_kg", lambda s: s.sum(min_count=1)),
    )
    summary["price_usd_per_kg"] = np.where(
        summary["net_weight_kg"].fillna(0) > 0,
        summary["fob_usd"] / summary["net_weight_kg"],
        np.nan,
    )
    return summary.sort_values("year").reset_index(drop=True)
