"""ETL: convierte los Excel de Trade Map y SUNAT a tablas en Turso.

Corre este script una sola vez (o cada vez que actualices los Excel en data/)
para poblar la base de datos en Turso. No hace falta correrlo en Vercel.

Uso:
    # Instalar dependencias de desarrollo (incluye openpyxl y pyarrow)
    pip install -e ".[dev]" openpyxl pyarrow

    # Configurar variables de entorno
    set TURSO_DATABASE_URL=libsql://<nombre>-<org>.turso.io
    set TURSO_AUTH_TOKEN=<tu-token>

    # Correr el ETL
    python scripts/etl_to_turso.py

    # Forzar recreación de tablas (borra datos existentes)
    python scripts/etl_to_turso.py --drop

El script es idempotente: puedes correrlo varias veces; los datos se
reemplazan (INSERT OR REPLACE) sin duplicar filas.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap: añadir src/ al path para importar el paquete sin instalar
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from exportanalysis.config import DATA_DIR  # noqa: E402
from exportanalysis.db.turso import TursoClient  # noqa: E402

# ---------------------------------------------------------------------------
# DDL: definición de tablas
# ---------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS peru_exports_ts (
    hs6           TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    partner_code  INTEGER,
    partner_name  TEXT,
    fob_usd       REAL,
    PRIMARY KEY (hs6, year, partner_code)
);

CREATE TABLE IF NOT EXISTS peru_exports_2025 (
    hs6                     TEXT    NOT NULL,
    partner_cd              TEXT,
    partner_code            INTEGER,
    partner_name            TEXT,
    is_world                INTEGER NOT NULL DEFAULT 0,
    fob_usd_thousand        REAL,
    quantity                REAL,
    quantity_unit           TEXT,
    quantity_kg             REAL,
    unit_value_usd_per_unit REAL,
    fob_usd                 REAL,
    PRIMARY KEY (hs6, partner_code)
);

CREATE TABLE IF NOT EXISTS world_exports (
    hs6           TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    reporter_code INTEGER,
    reporter_name TEXT,
    partner_cd    TEXT,
    partner_name  TEXT,
    fob_usd       REAL,
    PRIMARY KEY (hs6, year, reporter_code)
);

CREATE TABLE IF NOT EXISTS world_imports (
    hs6           TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    reporter_code INTEGER,
    reporter_name TEXT,
    cif_usd       REAL,
    PRIMARY KEY (hs6, year, reporter_code)
);

CREATE TABLE IF NOT EXISTS country_quantities (
    hs6           TEXT    NOT NULL,
    type          TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    reporter_code INTEGER,
    reporter_name TEXT,
    quantity_kg   REAL,
    PRIMARY KEY (hs6, type, year, reporter_code)
);

CREATE TABLE IF NOT EXISTS sunat_exports (
    nandina       TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    partner_label TEXT,
    fob_usd       REAL,
    net_weight_kg REAL
);
"""

DROP_DDL = """
DROP TABLE IF EXISTS peru_exports_ts;
DROP TABLE IF EXISTS peru_exports_2025;
DROP TABLE IF EXISTS world_exports;
DROP TABLE IF EXISTS world_imports;
DROP TABLE IF EXISTS country_quantities;
DROP TABLE IF EXISTS sunat_exports;
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _year_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if str(c).split(" ")[0].isdigit()]


def _safe(val):
    """Convierte NaN/Inf a None para que Turso los almacene como NULL."""
    if val is None:
        return None
    try:
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _find(hs6: str, pattern: str) -> Path | None:
    for p in DATA_DIR.rglob(pattern.format(hs6=hs6)):
        if "_cache" not in str(p):
            return p
    return None


def _nandina_files() -> list[Path]:
    """Archivos Excel de SUNAT (nombre = 10 dígitos)."""
    import re
    re_nandina = re.compile(r"^\d{10}\.xlsx$", re.IGNORECASE)
    return [p for p in DATA_DIR.rglob("*.xlsx") if re_nandina.match(p.name) and "_cache" not in str(p)]


# ---------------------------------------------------------------------------
# Loaders: cada función lee un Excel y devuelve un list[tuple] para INSERT
# ---------------------------------------------------------------------------

def load_peru_exports_ts(hs6: str) -> list[tuple]:
    path = _find(hs6, "perus-exports-to-world-by-importer_{hs6}.xlsx")
    if not path:
        return []
    df = pd.read_excel(path)
    year_cols = _year_columns(df)
    df_m = pd.melt(
        df,
        id_vars=["partnerCd", "partnerLabel"],
        value_vars=year_cols,
        var_name="year",
        value_name="fob_usd_thousand",
    )
    df_m["year"] = df_m["year"].astype(str).str.split(" ", n=1).str[0].astype(int)
    df_m["fob_usd"] = pd.to_numeric(df_m["fob_usd_thousand"], errors="coerce") * 1000.0
    df_m["partner_code"] = pd.to_numeric(df_m["partnerCd"], errors="coerce")
    rows = []
    for _, row in df_m.iterrows():
        rows.append((
            hs6,
            int(row["year"]),
            _safe(row["partner_code"]),
            str(row["partnerLabel"]) if pd.notna(row["partnerLabel"]) else None,
            _safe(row["fob_usd"]),
        ))
    return rows


def load_peru_exports_2025(hs6: str) -> list[tuple]:
    path = _find(hs6, "perus-exports-to-world-in-2025-by-importer_{hs6}.xlsx")
    if not path:
        return []
    df = pd.read_excel(path).copy()
    df["partnerCd"] = df["partnerCd"].astype(str).str.zfill(3)
    df["partner_code"] = pd.to_numeric(df["partnerCd"], errors="coerce")
    df["is_world"] = (df["partnerLabel"] == "World").astype(int)
    df["fob_usd_thousand"] = pd.to_numeric(df.get("Value (kUSD)"), errors="coerce")
    df["quantity"] = pd.to_numeric(df.get("Quantity"), errors="coerce")
    df["quantity_unit"] = df.get("Quantity Unit", "").astype(str)
    unit = df["quantity_unit"].str.lower()
    is_ton = unit.str.contains(r"ton|tne|mt\b", regex=True)
    df["quantity_kg"] = df["quantity"] * is_ton.map({True: 1000.0, False: 1.0})
    df["unit_value"] = pd.to_numeric(df.get("Unit Value"), errors="coerce")
    df["fob_usd"] = df["fob_usd_thousand"] * 1000.0

    rows = []
    for _, row in df.iterrows():
        rows.append((
            hs6,
            str(row["partnerCd"]),
            _safe(row["partner_code"]),
            str(row["partnerLabel"]) if pd.notna(row["partnerLabel"]) else None,
            int(row["is_world"]),
            _safe(row["fob_usd_thousand"]),
            _safe(row["quantity"]),
            str(row["quantity_unit"]) if pd.notna(row["quantity_unit"]) else None,
            _safe(row["quantity_kg"]),
            _safe(row["unit_value"]),
            _safe(row["fob_usd"]),
        ))
    return rows


def load_world_exports(hs6: str) -> list[tuple]:
    path = _find(hs6, "exporting-economies_{hs6}.xlsx")
    if not path:
        return []
    df = pd.read_excel(path)
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
    df_m["reporter_code"] = pd.to_numeric(df_m["reporterCd"], errors="coerce")
    df_m = df_m[df_m["reporter_code"] != 0]
    rows = []
    for _, row in df_m.iterrows():
        rows.append((
            hs6,
            int(row["year"]),
            _safe(row["reporter_code"]),
            str(row["reporterLabel"]) if pd.notna(row["reporterLabel"]) else None,
            str(row["partnerCd"]) if pd.notna(row["partnerCd"]) else None,
            str(row["partnerLabel"]) if pd.notna(row["partnerLabel"]) else None,
            _safe(row["fob_usd"]),
        ))
    return rows


def load_world_imports(hs6: str) -> list[tuple]:
    path = _find(hs6, "importing-economies_{hs6}.xlsx")
    if not path:
        return []
    df = pd.read_excel(path)
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
    df_m["reporter_code"] = pd.to_numeric(df_m["reporterCd"], errors="coerce")
    df_m = df_m[df_m["reporter_code"] != 0]
    rows = []
    for _, row in df_m.iterrows():
        rows.append((
            hs6,
            int(row["year"]),
            _safe(row["reporter_code"]),
            str(row["reporterLabel"]) if pd.notna(row["reporterLabel"]) else None,
            _safe(row["cif_usd"]),
        ))
    return rows


def _load_quantities(hs6: str, pattern: str, qtype: str) -> list[tuple]:
    path = _find(hs6, pattern)
    if not path:
        return []
    df = pd.read_excel(path)
    reporter_code = pd.to_numeric(df["reporterCd"], errors="coerce")
    partner_code = pd.to_numeric(df["partnerCd"], errors="coerce")
    frame = df[(partner_code == 0) & (reporter_code != 0)].copy()
    frame["reporter_code"] = reporter_code.loc[frame.index].astype("Int64")

    rows = []
    for col in df.columns:
        year = str(col)
        if not (len(year) == 4 and year.isdigit()):
            continue
        unit_col = f"{year}_unit"
        if unit_col not in frame.columns:
            continue
        quantity = pd.to_numeric(frame[col], errors="coerce")
        unit = frame[unit_col].astype(str).str.strip().str.lower()
        factor = pd.Series(float("nan"), index=frame.index, dtype=float)
        factor.loc[unit.str.contains("ton", na=False)] = 1000.0
        factor.loc[unit.str.contains(r"\bkg\b|kilogram", regex=True, na=False)] = 1.0
        qty_kg = quantity * factor

        for idx in frame.index:
            if pd.isna(qty_kg.loc[idx]):
                continue
            rows.append((
                hs6,
                qtype,
                int(year),
                _safe(frame.loc[idx, "reporter_code"]),
                str(frame.loc[idx, "reporterLabel"]) if pd.notna(frame.loc[idx, "reporterLabel"]) else None,
                _safe(qty_kg.loc[idx]),
            ))
    return rows


def load_sunat_exports(nandina: str, path: Path) -> list[tuple]:
    import re
    xls = pd.ExcelFile(path)
    frames = []
    for sheet in xls.sheet_names:
        label = str(sheet).strip()
        if not (len(label) == 4 and label.isdigit()):
            continue
        raw = pd.read_excel(path, sheet_name=sheet)
        if raw.empty:
            continue
        partner_col = raw.columns[0]
        fob_col = next(
            (c for c in raw.columns if "fob" in str(c).lower() and "%" not in str(c).lower()),
            None,
        )
        net_col = next(
            (c for c in raw.columns if "neto" in str(c).lower()),
            None,
        )
        if fob_col is None or net_col is None:
            continue
        for _, row in raw.iterrows():
            fob = pd.to_numeric(row[fob_col], errors="coerce")
            if pd.isna(fob):
                continue
            frames.append((
                nandina,
                int(label),
                str(row[partner_col]).strip() if pd.notna(row[partner_col]) else None,
                _safe(fob),
                _safe(pd.to_numeric(row[net_col], errors="coerce")),
            ))
    return frames


# ---------------------------------------------------------------------------
# Bulk insert helper
# ---------------------------------------------------------------------------

def bulk_insert(client: TursoClient, table: str, columns: list[str], rows: list[tuple], chunk: int = 100) -> int:
    """Inserta filas en lotes usando INSERT OR REPLACE."""
    if not rows:
        return 0
    placeholders = ", ".join("?" * len(columns))
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    inserted = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        for row in batch:
            client.execute(sql, list(row))
        inserted += len(batch)
    return inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ETL: Excel → Turso")
    parser.add_argument("--drop", action="store_true", help="Elimina y recrea todas las tablas antes de insertar")
    args = parser.parse_args()

    if not os.getenv("TURSO_DATABASE_URL") or not os.getenv("TURSO_AUTH_TOKEN"):
        print("❌ Faltan variables de entorno: TURSO_DATABASE_URL y TURSO_AUTH_TOKEN")
        sys.exit(1)

    print("🔌 Conectando a Turso...")
    client = TursoClient()

    if args.drop:
        print("🗑️  Eliminando tablas existentes...")
        for stmt in DROP_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                client.execute(stmt)

    print("🏗️  Creando tablas (si no existen)...")
    for stmt in DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            client.execute(stmt)

    # Descubrir todos los HS6 disponibles en data/
    hs6_set: set[str] = set()
    import re as _re
    _HS6_RE = _re.compile(r"(\d{6})")
    for folder in DATA_DIR.rglob("*"):
        if folder.is_dir() and "_cache" not in str(folder):
            m = _HS6_RE.match(folder.name.strip())
            if m:
                hs6_set.add(m.group(1))

    print(f"\n📦 Productos encontrados: {len(hs6_set)}")
    total_rows = 0

    for hs6 in sorted(hs6_set):
        print(f"\n  HS6 {hs6}:")
        t0 = time.time()

        # 1. Peru exports time series
        rows = load_peru_exports_ts(hs6)
        n = bulk_insert(client, "peru_exports_ts",
                        ["hs6", "year", "partner_code", "partner_name", "fob_usd"], rows)
        print(f"    peru_exports_ts:    {n:>5} filas")
        total_rows += n

        # 2. Peru exports 2025 snapshot
        rows = load_peru_exports_2025(hs6)
        n = bulk_insert(client, "peru_exports_2025",
                        ["hs6", "partner_cd", "partner_code", "partner_name", "is_world",
                         "fob_usd_thousand", "quantity", "quantity_unit", "quantity_kg",
                         "unit_value_usd_per_unit", "fob_usd"], rows)
        print(f"    peru_exports_2025:  {n:>5} filas")
        total_rows += n

        # 3. World exports
        rows = load_world_exports(hs6)
        n = bulk_insert(client, "world_exports",
                        ["hs6", "year", "reporter_code", "reporter_name",
                         "partner_cd", "partner_name", "fob_usd"], rows)
        print(f"    world_exports:      {n:>5} filas")
        total_rows += n

        # 4. World imports
        rows = load_world_imports(hs6)
        n = bulk_insert(client, "world_imports",
                        ["hs6", "year", "reporter_code", "reporter_name", "cif_usd"], rows)
        print(f"    world_imports:      {n:>5} filas")
        total_rows += n

        # 5. Import quantities
        rows = _load_quantities(hs6, "kg_importing-economies_{hs6}.xlsx", "import")
        n = bulk_insert(client, "country_quantities",
                        ["hs6", "type", "year", "reporter_code", "reporter_name", "quantity_kg"], rows)
        print(f"    import quantities:  {n:>5} filas")
        total_rows += n

        # 6. Export quantities
        rows = _load_quantities(hs6, "kg_exporting-economies_{hs6}.xlsx", "export")
        n = bulk_insert(client, "country_quantities",
                        ["hs6", "type", "year", "reporter_code", "reporter_name", "quantity_kg"], rows)
        print(f"    export quantities:  {n:>5} filas")
        total_rows += n

        print(f"    ⏱  {time.time() - t0:.1f}s")

    # SUNAT
    print("\n  SUNAT:")
    for path in _nandina_files():
        nandina = path.stem
        rows = load_sunat_exports(nandina, path)
        n = bulk_insert(client, "sunat_exports",
                        ["nandina", "year", "partner_label", "fob_usd", "net_weight_kg"], rows)
        print(f"    {nandina}: {n:>5} filas")
        total_rows += n

    client.close()
    print(f"\n✅ ETL completado: {total_rows:,} filas insertadas en Turso.")


if __name__ == "__main__":
    main()
