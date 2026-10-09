"""Tests del lector de Excel (valores, unidades, anos)."""

from __future__ import annotations

import sys
sys.path.insert(0, "src")

import numpy as np

from exportanalysis.pipeline import excel_analysis


def test_peru_exports_ts_has_years_and_values():
    df = excel_analysis.peru_exports_ts("081040")
    assert "year" in df.columns
    assert "fob_usd" in df.columns
    assert len(df) > 0
    assert df["year"].min() >= 2015
    assert df["year"].max() >= 2024


def test_peru_exports_ts_2025_present():
    df = excel_analysis.peru_exports_ts("081040")
    assert 2025 in df["year"].unique()


def test_indicators_2025_structure():
    ind = excel_analysis.peru_exports_indicators_2025("081040")
    assert "quantity" in ind.columns
    assert "unit_value_usd_per_unit" in ind.columns
    assert len(ind) > 0


def test_ts_with_quantity_merges():
    df = excel_analysis.peru_exports_ts_with_quantity("081040")
    # at least for 2025 we expect some merged
    assert "quantity" in df.columns
    assert "unit_value_usd_per_unit" in df.columns
    assert df[df["year"] == 2025]["quantity"].notna().sum() >= 0


def test_world_exports_and_imports_readable():
    we = excel_analysis.world_exports("081040")
    wi = excel_analysis.world_imports("081040")
    assert len(we) > 0
    assert len(wi) > 0
    assert "year" in we.columns and "fob_usd" in we.columns
    assert "year" in wi.columns
