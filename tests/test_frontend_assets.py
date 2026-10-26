"""Tests de los iconos del frontend.

El favicon es facil de romper sin darse cuenta: un comentario XML con `--`
invalida el SVG entero, y si los archivos se mueven fuera de `assets/` FastAPI
deja de servirlos (solo monta `dist/assets/`). Estos tests cubren las dos cosas.

No usan Pillow: validan los archivos versionados, que son los que se publican.
Regenerarlos es un paso manual y documentado (`scripts/make_favicon.py`).
"""

from __future__ import annotations

import struct
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "frontend" / "public" / "assets"
SVG = ASSETS / "favicon.svg"
PNG = ASSETS / "apple-touch-icon.png"
ICO = ASSETS / "favicon.ico"
INDEX = ROOT / "frontend" / "index.html"


def test_el_svg_es_xml_valido():
    """XML no admite `--` dentro de comentarios; un solo guion doble rompe el icono."""
    root = ET.parse(SVG).getroot()
    assert root.tag.endswith("svg")
    assert root.get("viewBox") == "0 0 64 64"


def test_el_svg_tiene_fondo_y_hoja():
    root = ET.parse(SVG).getroot()
    tags = [el.tag.split("}")[-1] for el in root.iter()]
    assert "rect" in tags, "falta el fondo redondeado"
    assert "path" in tags, "falta la hoja"


def test_apple_touch_icon_es_png_de_180():
    data = PNG.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "no es un PNG"
    width, height = struct.unpack_from(">II", data, 16)
    assert (width, height) == (180, 180)


def test_el_ico_trae_los_tres_tamanos():
    data = ICO.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind) == (0, 1), "no es un ICO"
    sizes = []
    for i in range(count):
        width = data[6 + i * 16] or 256
        height = data[7 + i * 16] or 256
        sizes.append((width, height))
    assert sorted(sizes) == [(16, 16), (32, 32), (48, 48)]


@pytest.mark.parametrize(
    "href",
    ["/assets/favicon.svg", "/assets/favicon.ico", "/assets/apple-touch-icon.png"],
)
def test_el_html_enlaza_los_iconos_bajo_assets(href: str):
    """Bajo /assets porque es el unico static mount de la API."""
    assert href in INDEX.read_text(encoding="utf-8")


def test_el_html_declara_el_color_de_marca():
    assert 'name="theme-color"' in INDEX.read_text(encoding="utf-8")
