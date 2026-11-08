"""Capa de acceso a datos de Trade Map: Turso en producción, Excel en local.

En producción (Vercel + Turso) las variables TURSO_DATABASE_URL y
TURSO_AUTH_TOKEN están definidas: todas las funciones leen desde la base de
datos en lugar de los archivos Excel. El motor de análisis (pipeline/) no
cambia: recibe los mismos DataFrames independientemente del origen.

En desarrollo local sin Turso, el comportamiento original se conserva: se
leen los Excel de data/ con pandas. No hace falta ninguna variable de entorno
ni conexión a internet para correr en local.

Esquema de Turso (ver scripts/etl_to_turso.py):
    peru_exports_ts       — serie histórica de exportaciones peruanas
    peru_exports_2025     — snapshot 2025 con volumen y precio unitario
    world_exports         — exportadores mundiales por año
    world_imports         — importadores mundiales por año
    country_quantities    — cantidades (import/export) normalizadas a kg
    sunat_exports         — exportaciones por destino desde Excel de SUNAT
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from .._cache import read_excel_cached
from ..config import DATA_DIR
from ..db.turso import _turso_configured, turso_client

# ---------------------------------------------------------------------------
# Resolución de rutas (modo Excel local)
# ---------------------------------------------------------------------------

_find_cache: dict[tuple[str, str], Path] = {}
_nandina_cache: dict[str, Path] = {}


def _find(hs6: str, pattern: str) -> Path:
    """Busca un Excel por HS6 en data/, ignorando la carpeta de cache."""
    key = (hs6, pattern)
    cached = _find_cache.get(key)
    if cached is not None:
        return cached
    for p in DATA_DIR.rglob(pattern.format(hs6=hs6)):
        if "_cache" not in str(p):
            _find_cache[key] = p
            return p
    raise FileNotFoundError(pattern.format(hs6=hs6))


TRADEMAP_FILES: dict[str, str] = {
    "exportadores": "exporting-economies_{hs6}.xlsx",
    "importadores": "importing-economies_{hs6}.xlsx",
    "serie_peru": "perus-exports-to-world-by-importer_{hs6}.xlsx",
    "snapshot_2025": "perus-exports-to-world-in-2025-by-importer_{hs6}.xlsx",
}

_IMPORT_QUANTITY_PATTERN = "kg_importing-economies_{hs6}.xlsx"
_EXPORT_QUANTITY_PATTERN = "kg_exporting-economies_{hs6}.xlsx"


def _year_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if str(c).split(" ")[0].isdigit()]


# ---------------------------------------------------------------------------
# data_files_status y data_token (invariantes de origen)
# ---------------------------------------------------------------------------

def data_files_status(hs6: str, nandina: str | None = None) -> dict:
    """Semáforo de confianza: qué archivos están disponibles para un HS6."""
    if _turso_configured():
        # En modo Turso: verificar que las tablas tienen datos para este hs6
        client = turso_client()
        checks = {}
        for key in TRADEMAP_FILES:
            table_map = {
                "exportadores": "world_exports",
                "importadores": "world_imports",
                "serie_peru": "peru_exports_ts",
                "snapshot_2025": "peru_exports_2025",
            }
            df = client.query_df(
                f"SELECT COUNT(*) as n FROM {table_map[key]} WHERE hs6 = ? LIMIT 1",
                [hs6],
            )
            checks[key] = int(df["n"].iloc[0]) > 0 if not df.empty else False

        import_qty = int(client.query_df(
            "SELECT COUNT(*) as n FROM country_quantities WHERE hs6 = ? AND type = 'import' LIMIT 1",
            [hs6],
        )["n"].iloc[0]) > 0

        export_qty = int(client.query_df(
            "SELECT COUNT(*) as n FROM country_quantities WHERE hs6 = ? AND type = 'export' LIMIT 1",
            [hs6],
        )["n"].iloc[0]) > 0

        sunat = False
        if nandina:
            df = client.query_df(
                "SELECT COUNT(*) as n FROM sunat_exports WHERE nandina = ? LIMIT 1",
                [nandina],
            )
            sunat = int(df["n"].iloc[0]) > 0 if not df.empty else False

        return {
            "trademap": checks,
            "trademap_count": sum(checks.values()),
            "trademap_expected": len(TRADEMAP_FILES),
            "importer_quantities": import_qty,
            "exporter_quantities": export_qty,
            "sunat": sunat,
        }

    # Modo Excel local
    present = {}
    for key, pattern in TRADEMAP_FILES.items():
        try:
            _find(hs6, pattern)
            present[key] = True
        except FileNotFoundError:
            present[key] = False

    sunat = False
    if nandina:
        try:
            _find_nandina_file(nandina)
            sunat = True
        except FileNotFoundError:
            sunat = False

    return {
        "trademap": present,
        "trademap_count": sum(present.values()),
        "trademap_expected": len(TRADEMAP_FILES),
        "importer_quantities": _has_import_quantities(hs6),
        "exporter_quantities": _has_export_quantities(hs6),
        "sunat": sunat,
    }


def _has_import_quantities(hs6: str) -> bool:
    try:
        _find(hs6, _IMPORT_QUANTITY_PATTERN)
        return True
    except FileNotFoundError:
        return False


def _has_export_quantities(hs6: str) -> bool:
    try:
        _find(hs6, _EXPORT_QUANTITY_PATTERN)
        return True
    except FileNotFoundError:
        return False


def data_token(hs6: str, nandina: str | None = None) -> tuple:
    """Huella de los datos: sirve para invalidar cachés derivados."""
    if _turso_configured():
        # En modo Turso: usar "turso" como marcador fijo (los datos no cambian en disco)
        return ("turso", hs6, nandina)

    parts: list = []
    for pattern in TRADEMAP_FILES.values():
        try:
            parts.append((pattern, _find(hs6, pattern).stat().st_mtime_ns))
        except FileNotFoundError:
            parts.append((pattern, None))
    for quantity_pattern in (_IMPORT_QUANTITY_PATTERN, _EXPORT_QUANTITY_PATTERN):
        try:
            parts.append((quantity_pattern, _find(hs6, quantity_pattern).stat().st_mtime_ns))
        except FileNotFoundError:
            parts.append((quantity_pattern, None))
    if nandina:
        try:
            parts.append(("sunat", _find_nandina_file(nandina).stat().st_mtime_ns))
        except FileNotFoundError:
            parts.append(("sunat", None))
    return tuple(parts)


# ---------------------------------------------------------------------------
# Funciones de acceso a datos — leen de Turso o de Excel según el entorno
# ---------------------------------------------------------------------------

def peru_exports_ts(hs6: str) -> pd.DataFrame:
    """Exportaciones peruanas por socio (serie histórica, valor en USD)."""
    if _turso_configured():
        df = turso_client().query_df(
            "SELECT year, partner_code, partner_name, fob_usd "
            "FROM peru_exports_ts WHERE hs6 = ? AND partner_code != 0",
            [hs6],
        )
        if df.empty:
            return pd.DataFrame(columns=["year", "partnerCd", "partnerLabel", "fob_usd"])
        df = df.rename(columns={"partner_code": "partnerCd", "partner_name": "partnerLabel"})
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["fob_usd"] = pd.to_numeric(df["fob_usd"], errors="coerce")
        return df[["year", "partnerCd", "partnerLabel", "fob_usd"]].dropna(subset=["fob_usd"])

    p = _find(hs6, "perus-exports-to-world-by-importer_{hs6}.xlsx")
    df = read_excel_cached(p)
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


def peru_exports_trade(hs6: str, nandina: str | None = None) -> pd.DataFrame:
    """Exportaciones peruanas por destino (incluye total World, con volumen)."""
    if _turso_configured():
        client = turso_client()
        df = client.query_df(
            "SELECT year, partner_code, partner_name, is_world, fob_usd "
            "FROM peru_exports_ts WHERE hs6 = ?",
            [hs6],
        )
        if df.empty:
            return pd.DataFrame(columns=["year", "partner_code", "partner_name", "is_world", "fob_usd", "net_weight_kg"])

        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["partner_code"] = pd.to_numeric(df["partner_code"], errors="coerce").astype("Int64")
        df["fob_usd"] = pd.to_numeric(df["fob_usd"], errors="coerce")
        df["is_world"] = df["partner_code"] == 0
        df["net_weight_kg"] = np.nan

        # Volumen 2025 desde snapshot
        try:
            ind = peru_exports_indicators_2025(hs6, include_world=True)
            qty = {
                int(code): float(kg)
                for code, kg in zip(ind["partner_code"], ind["quantity_kg"], strict=False)
                if pd.notna(kg) and pd.notna(code)
            }
            is_latest = df["year"] == 2025
            mapped = df.loc[is_latest, "partner_code"].map(qty)
            df.loc[is_latest, "net_weight_kg"] = mapped.to_numpy(dtype="float64", na_value=np.nan)
        except (KeyError, ValueError):
            pass

        # Volumen histórico desde SUNAT
        if nandina:
            try:
                sunat_summary = sunat_annual_summary(nandina)
                sunat_vol = {
                    int(row["year"]): float(row["net_weight_kg"])
                    for _, row in sunat_summary.iterrows()
                    if pd.notna(row["net_weight_kg"])
                }
                is_world = df["is_world"]
                for year, vol in sunat_vol.items():
                    mask = is_world & (df["year"] == year)
                    if mask.any():
                        df.loc[mask, "net_weight_kg"] = vol
            except (KeyError, ValueError):
                pass

        return (
            df[["year", "partner_code", "partner_name", "is_world", "fob_usd", "net_weight_kg"]]
            .sort_values(["year", "fob_usd"], ascending=[True, False])
            .reset_index(drop=True)
        )

    # Modo Excel local (código original)
    p = _find(hs6, "perus-exports-to-world-by-importer_{hs6}.xlsx")
    df = read_excel_cached(p)
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

    try:
        ind = peru_exports_indicators_2025(hs6, include_world=True)
        qty = {
            int(code): float(kg)
            for code, kg in zip(ind["partner_code"], ind["quantity_kg"], strict=False)
            if pd.notna(kg) and pd.notna(code)
        }
        is_latest = melted["year"] == 2025
        mapped = melted.loc[is_latest, "partner_code"].map(qty)
        melted.loc[is_latest, "net_weight_kg"] = mapped.to_numpy(dtype="float64", na_value=np.nan)
    except (FileNotFoundError, KeyError, ValueError):
        pass

    if nandina:
        try:
            sunat_summary = sunat_annual_summary(nandina)
            sunat_vol = {
                int(row["year"]): float(row["net_weight_kg"])
                for _, row in sunat_summary.iterrows()
                if pd.notna(row["net_weight_kg"])
            }
            is_world = melted["is_world"]
            for year, vol in sunat_vol.items():
                mask = is_world & (melted["year"] == year)
                if mask.any():
                    melted.loc[mask, "net_weight_kg"] = vol
        except (FileNotFoundError, KeyError, ValueError):
            pass

    return (
        melted[["year", "partner_code", "partner_name", "is_world", "fob_usd", "net_weight_kg"]]
        .sort_values(["year", "fob_usd"], ascending=[True, False])
        .reset_index(drop=True)
    )


def world_exports(hs6: str) -> pd.DataFrame:
    """Exportaciones por país exportador (serie histórica)."""
    if _turso_configured():
        df = turso_client().query_df(
            "SELECT year, reporter_code, reporter_name, partner_cd, partner_name, fob_usd "
            "FROM world_exports WHERE hs6 = ?",
            [hs6],
        )
        if df.empty:
            return pd.DataFrame(columns=["year", "reporterCd", "reporterLabel", "partnerCd", "partnerLabel", "fob_usd"])
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["fob_usd"] = pd.to_numeric(df["fob_usd"], errors="coerce")
        df = df.rename(columns={
            "reporter_code": "reporterCd",
            "reporter_name": "reporterLabel",
            "partner_cd": "partnerCd",
            "partner_name": "partnerLabel",
        })
        return df.reset_index(drop=True)

    p = _find(hs6, "exporting-economies_{hs6}.xlsx")
    df = read_excel_cached(p)
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
    reporter_code = pd.to_numeric(df_m["reporterCd"], errors="coerce")
    return df_m[reporter_code != 0].reset_index(drop=True)


def world_imports(hs6: str) -> pd.DataFrame:
    """Importaciones por país importador (serie histórica)."""
    if _turso_configured():
        df = turso_client().query_df(
            "SELECT year, reporter_code, reporter_name, cif_usd "
            "FROM world_imports WHERE hs6 = ?",
            [hs6],
        )
        if df.empty:
            return pd.DataFrame(columns=["year", "reporterCd", "reporterLabel", "cif_usd"])
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["cif_usd"] = pd.to_numeric(df["cif_usd"], errors="coerce")
        df = df.rename(columns={"reporter_code": "reporterCd", "reporter_name": "reporterLabel"})
        return df.reset_index(drop=True)

    p = _find(hs6, "importing-economies_{hs6}.xlsx")
    df = read_excel_cached(p)
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
    reporter_code = pd.to_numeric(df_m["reporterCd"], errors="coerce")
    return df_m[reporter_code != 0].reset_index(drop=True)


def world_import_quantities(hs6: str) -> pd.DataFrame:
    """Cantidad importada por país y año, normalizada a kilos."""
    return _country_quantities(hs6, "import")


def world_export_quantities(hs6: str) -> pd.DataFrame:
    """Cantidad exportada por país y año, normalizada a kilos."""
    return _country_quantities(hs6, "export")


def _country_quantities(hs6: str, qtype: str) -> pd.DataFrame:
    """Cantidad por país reportero y año desde Turso o Excel."""
    if _turso_configured():
        df = turso_client().query_df(
            "SELECT year, reporter_code, reporter_name, quantity_kg "
            "FROM country_quantities WHERE hs6 = ? AND type = ?",
            [hs6, qtype],
        )
        if df.empty:
            return pd.DataFrame(columns=["reporter_code", "reporter_name", "year", "quantity_kg"])
        df = df.rename(columns={"reporter_code": "reporter_code", "reporter_name": "reporter_name"})
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["quantity_kg"] = pd.to_numeric(df["quantity_kg"], errors="coerce")
        return df.dropna(subset=["quantity_kg"]).reset_index(drop=True)

    pattern = _IMPORT_QUANTITY_PATTERN if qtype == "import" else _EXPORT_QUANTITY_PATTERN
    p = _find(hs6, pattern)
    df = read_excel_cached(p)
    reporter_code = pd.to_numeric(df["reporterCd"], errors="coerce")
    partner_code = pd.to_numeric(df["partnerCd"], errors="coerce")
    frame = df[(partner_code == 0) & (reporter_code != 0)].copy()
    frame["reporter_code"] = reporter_code.loc[frame.index].astype("Int64")

    rows: list[pd.DataFrame] = []
    for column in df.columns:
        year = str(column)
        if not (len(year) == 4 and year.isdigit()):
            continue
        unit_column = f"{year}_unit"
        if unit_column not in frame.columns:
            continue
        quantity = pd.to_numeric(frame[column], errors="coerce")
        unit = frame[unit_column].astype(str).str.strip().str.lower()
        factor = pd.Series(np.nan, index=frame.index, dtype=float)
        factor.loc[unit.str.contains("ton", na=False)] = 1000.0
        factor.loc[unit.str.contains(r"\bkg\b|kilogram", regex=True, na=False)] = 1.0

        annual = pd.DataFrame(
            {
                "reporter_code": frame["reporter_code"],
                "reporter_name": frame["reporterLabel"],
                "year": int(year),
                "quantity_kg": quantity * factor,
            },
            index=frame.index,
        )
        rows.append(annual)

    if not rows:
        return pd.DataFrame(columns=["reporter_code", "reporter_name", "year", "quantity_kg"])
    return pd.concat(rows, ignore_index=True).dropna(subset=["quantity_kg"])


def peru_exports_indicators_2025(hs6: str, *, include_world: bool = False) -> pd.DataFrame:
    """Snapshot 2025 por destino: Value (kUSD), Quantity, Unit Value."""
    if _turso_configured():
        sql = "SELECT * FROM peru_exports_2025 WHERE hs6 = ?"
        if not include_world:
            sql += " AND is_world = 0"
        df = turso_client().query_df(sql, [hs6])
        if df.empty:
            return pd.DataFrame(columns=["partnerCd", "partner_code", "partnerLabel",
                                          "fob_usd_thousand", "quantity", "quantity_unit",
                                          "quantity_kg", "unit_value_usd_per_unit", "fob_usd", "year"])
        df["fob_usd_thousand"] = pd.to_numeric(df["fob_usd_thousand"], errors="coerce")
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        df["quantity_kg"] = pd.to_numeric(df["quantity_kg"], errors="coerce")
        df["unit_value_usd_per_unit"] = pd.to_numeric(df["unit_value_usd_per_unit"], errors="coerce")
        df["fob_usd"] = pd.to_numeric(df["fob_usd"], errors="coerce")
        df["partner_code"] = pd.to_numeric(df["partner_code"], errors="coerce").astype("Int64")
        df["year"] = 2025
        df = df.rename(columns={
            "partner_cd": "partnerCd",
            "partner_name": "partnerLabel",
        })
        return df

    p = _find(hs6, "perus-exports-to-world-in-2025-by-importer_{hs6}.xlsx")
    df = read_excel_cached(p).copy()
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
    is_ton = unit.str.contains(r"ton|tne|mt\b", regex=True)
    out["quantity_kg"] = out["quantity"] * is_ton.map({True: 1000.0, False: 1.0})
    out["fob_usd"] = out["fob_usd_thousand"] * 1000.0
    out["year"] = 2025
    return out


def peru_exports_ts_with_quantity(hs6: str) -> pd.DataFrame:
    """Serie por destino con la cantidad (kg) de 2025 donde exista."""
    ts = peru_exports_ts(hs6).copy()
    # Normalizar nombre de columna para merge
    if "partnerCd" not in ts.columns and "partner_code" in ts.columns:
        ts["partnerCd"] = ts["partner_code"].astype(str).str.zfill(3)
    ts["partnerCd"] = ts["partnerCd"].astype(str).str.zfill(3)
    try:
        ind = peru_exports_indicators_2025(hs6)
        if "partnerCd" not in ind.columns and "partner_cd" in ind.columns:
            ind = ind.rename(columns={"partner_cd": "partnerCd"})
        ind = ind[["partnerCd", "year", "quantity", "quantity_kg", "unit_value_usd_per_unit"]]
        return ts.merge(ind, on=["partnerCd", "year"], how="left")
    except (FileNotFoundError, KeyError):
        return ts


def available_years(hs6: str) -> list[int]:
    """Años con data en la serie histórica, ordenados."""
    df = peru_exports_ts(hs6)
    return sorted(df["year"].dropna().astype(int).unique().tolist())


# ---------------------------------------------------------------------------
# SUNAT
# ---------------------------------------------------------------------------

def _find_nandina_file(nandina: str) -> Path:
    cached = _nandina_cache.get(nandina)
    if cached is not None:
        return cached
    for p in DATA_DIR.rglob(f"{nandina}.xlsx"):
        if "_cache" not in str(p):
            _nandina_cache[nandina] = p
            return p
    raise FileNotFoundError(f"{nandina}.xlsx")


def _column_by(cols: list, *needles: str, exclude: tuple[str, ...] = ()) -> str | None:
    for col in cols:
        text = str(col).lower()
        if all(n in text for n in needles) and not any(e in text for e in exclude):
            return col
    return None


def sunat_exports_by_nandina(nandina: str) -> pd.DataFrame:
    """Exportaciones por destino desde Turso o Excel de SUNAT."""
    if _turso_configured():
        df = turso_client().query_df(
            "SELECT year, partner_label, fob_usd, net_weight_kg "
            "FROM sunat_exports WHERE nandina = ?",
            [nandina],
        )
        if df.empty:
            return pd.DataFrame(columns=["year", "partner_label", "fob_usd", "net_weight_kg"])
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["fob_usd"] = pd.to_numeric(df["fob_usd"], errors="coerce")
        df["net_weight_kg"] = pd.to_numeric(df["net_weight_kg"], errors="coerce")
        return df.dropna(subset=["fob_usd"]).reset_index(drop=True)

    path = _find_nandina_file(nandina)
    xls = pd.ExcelFile(path)
    frames: list[pd.DataFrame] = []
    for sheet in xls.sheet_names:
        label = str(sheet).strip()
        if not (len(label) == 4 and label.isdigit()):
            continue
        raw = pd.read_excel(path, sheet_name=sheet)
        if raw.empty:
            continue
        cols = raw.columns.tolist()
        partner_col = cols[0]
        fob_col = _column_by(cols, "fob", exclude=("%",))
        net_col = _column_by(cols, "neto")
        if fob_col is None or net_col is None:
            continue
        sub = raw[[partner_col, fob_col, net_col]].copy()
        sub.columns = ["partner_label", "fob_usd", "net_weight_kg"]
        sub["fob_usd"] = pd.to_numeric(sub["fob_usd"], errors="coerce")
        sub["net_weight_kg"] = pd.to_numeric(sub["net_weight_kg"], errors="coerce")
        sub = sub.dropna(subset=["fob_usd"])
        sub["year"] = int(label)
        frames.append(sub[["year", "partner_label", "fob_usd", "net_weight_kg"]])

    if not frames:
        return pd.DataFrame(columns=["year", "partner_label", "fob_usd", "net_weight_kg"])
    return pd.concat(frames, ignore_index=True)


def sunat_annual_summary(nandina: str) -> pd.DataFrame:
    """Resumen anual de exportaciones SUNAT (total por año, peso neto kg)."""
    df = sunat_exports_by_nandina(nandina)
    if df.empty:
        return pd.DataFrame(columns=["year", "fob_usd", "net_weight_kg"])
    summary = (
        df.groupby("year", as_index=False)
        .agg(fob_usd=("fob_usd", "sum"), net_weight_kg=("net_weight_kg", "sum"))
        .sort_values("year")
        .reset_index(drop=True)
    )
    return summary
