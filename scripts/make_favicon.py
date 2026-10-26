#!/usr/bin/env python
"""Genera el PNG y el ICO del favicon a partir de `frontend/public/assets/favicon.svg`.

El SVG es la unica fuente de verdad: este script lo lee, rasteriza la misma
geometria y escribe los formatos que algunos navegadores todavia piden.

    python scripts/make_favicon.py            # regenera y valida
    python scripts/make_favicon.py --check    # solo valida que esten al dia

Requiere Pillow (`pip install pillow`), que NO es dependencia de la app: solo
hace falta para regenerar los iconos. Los archivos generados se versionan, asi
que el build y el runtime no necesitan Pillow.

Salidas, en `frontend/public/assets/`:
  - apple-touch-icon.png  180x180 opaco, fondo a sangre (iOS aplica su mascara)
  - favicon.ico           16/32/48 px, con transparencia en las esquinas
El navegador prefiere `favicon.svg`; el .ico es el respaldo.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "frontend" / "public" / "assets"
SVG_PATH = ASSETS / "favicon.svg"
APPLE_PATH = ASSETS / "apple-touch-icon.png"
ICO_PATH = ASSETS / "favicon.ico"


# --------------------------------------------------------------------------- #
# Lectura del SVG
# --------------------------------------------------------------------------- #
def _tag(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def _color(value: str | None) -> tuple[int, int, int, int] | None:
    if not value or value == "none":
        return None
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", value.strip())
    if not m:
        raise SystemExit(f"color no soportado: {value!r}")
    n = int(m.group(1), 16)
    return (n >> 16 & 255, n >> 8 & 255, n & 255, 255)


_TOKEN = re.compile(
    r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)"
)


@dataclass
class SubPath:
    points: list[tuple[float, float]]
    fill: tuple[int, int, int, int] | None
    stroke: tuple[int, int, int, int] | None
    width: float


def _cubic(p0, p1, p2, p3, steps: int = 64):
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return out


def _arc(p0, rx, ry, phi_deg, large, sweep, p1, steps: int = 96):
    """Arco de elipse SVG (implementacion de la spec, F.6.5)."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)

    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = cos_p * dx + sin_p * dy
    y1 = -sin_p * dx + cos_p * dy

    rx, ry = abs(rx), abs(ry)
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s

    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cx1 = coef * rx * y1 / ry
    cy1 = -coef * ry * x1 / rx

    cx = cos_p * cx1 - sin_p * cy1 + (p0[0] + p1[0]) / 2
    cy = sin_p * cx1 + cos_p * cy1 + (p0[1] + p1[1]) / 2

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, dot / n))) if n else 0.0
        return -a if ux * vy - uy * vx < 0 else a

    ux, uy = (x1 - cx1) / rx, (y1 - cy1) / ry
    vx, vy = (-x1 - cx1) / rx, (-y1 - cy1) / ry
    theta = angle(1, 0, ux, uy)
    delta = angle(ux, uy, vx, vy)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    out = []
    for i in range(1, steps + 1):
        t = theta + delta * i / steps
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cos_p * x - sin_p * y + cx, sin_p * x + cos_p * y + cy))
    return out


def _parse_path(d: str) -> list[list[tuple[float, float]]]:
    tokens: list[str] = []
    for cmd, num in _TOKEN.findall(d):
        tokens.append(cmd or num)

    subpaths: list[list[tuple[float, float]]] = []
    pts: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    i = 0
    cmd = ""

    def num() -> float:
        nonlocal i
        val = float(tokens[i])
        i += 1
        return val

    if "A" in d or "a" in d:
        pass  # solo documenta que los arcos estan soportados

    while i < len(tokens):
        if _TOKEN.fullmatch(tokens[i]) and tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if pts:
                    pts.append(start)
                    subpaths.append(pts)
                    pts = []
                cur = start
                continue
        if not cmd:
            raise SystemExit(f"path sin comando: {d!r}")

        rel = cmd.islower()
        op = cmd.upper()
        if op == "M":
            x, y = num(), num()
            if rel:
                x, y = cur[0] + x, cur[1] + y
            if pts:
                subpaths.append(pts)
            cur = start = (x, y)
            pts = [cur]
            cmd = "l" if rel else "L"  # el resto de un M son lineas
        elif op == "L":
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.append(cur)
        elif op == "H":
            x = num()
            cur = (cur[0] + x if rel else x, cur[1])
            pts.append(cur)
        elif op == "V":
            y = num()
            cur = (cur[0], cur[1] + y if rel else y)
            pts.append(cur)
        elif op == "C":
            p1 = (num(), num())
            p2 = (num(), num())
            p3 = (num(), num())
            if rel:
                p1 = (cur[0] + p1[0], cur[1] + p1[1])
                p2 = (cur[0] + p2[0], cur[1] + p2[1])
                p3 = (cur[0] + p3[0], cur[1] + p3[1])
            pts.extend(_cubic(cur, p1, p2, p3))
            cur = p3
        elif op == "A":
            rx, ry, rot = num(), num(), num()
            large, sweep = int(num()), int(num())
            p = (num(), num())
            if rel:
                p = (cur[0] + p[0], cur[1] + p[1])
            pts.extend(_arc(cur, rx, ry, rot, large, sweep, p))
            cur = p
        else:
            raise SystemExit(f"comando SVG no soportado: {cmd!r} en {d!r}")
    if pts:
        subpaths.append(pts)
    return subpaths


def _transform(spec: str) -> tuple[float, float, float, float]:
    tx = ty = 0.0
    sx = sy = 1.0
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", spec):
        nums = [float(v) for v in re.split(r"[,\s]+", args.strip()) if v]
        if name == "translate":
            tx += nums[0]
            ty += nums[1] if len(nums) > 1 else 0.0
        elif name == "scale":
            sx *= nums[0]
            sy *= nums[1] if len(nums) > 1 else nums[0]
        else:
            raise SystemExit(f"transform no soportado: {name}")
    return tx, ty, sx, sy


@dataclass
class Icon:
    size: float
    radius: float
    background: tuple[int, int, int, int]
    shapes: list[SubPath]


def load_svg(path: Path) -> Icon:
    root = ET.parse(path).getroot()
    size = float(root.get("viewBox", "0 0 64 64").split()[2])
    background = None
    radius = 0.0
    transform = (0.0, 0.0, 1.0, 1.0)
    shapes: list[SubPath] = []

    for el in root.iter():
        tag = _tag(el)
        if tag == "rect":
            background = _color(el.get("fill"))
            radius = float(el.get("rx") or 0)
            size = float(el.get("width") or size)
        elif tag == "g":
            transform = _transform(el.get("transform") or "")

    tx, ty, sx, sy = transform
    for el in root.iter():
        if _tag(el) != "path":
            continue
        fill = _color(el.get("fill"))
        stroke = _color(el.get("stroke"))
        width = float(el.get("stroke-width") or 0) * (sx + sy) / 2
        for pts in _parse_path(el.get("d") or ""):
            moved = [(tx + sx * x, ty + sy * y) for x, y in pts]
            shapes.append(SubPath(moved, fill, stroke, width))

    if background is None:
        raise SystemExit("el SVG no tiene <rect> de fondo")
    return Icon(size, radius, background, shapes)


# --------------------------------------------------------------------------- #
# Rasterizado
# --------------------------------------------------------------------------- #
def render(icon: Icon, size: int, *, rounded: bool, ss: int = 8) -> Image.Image:
    """Dibuja a `size*ss` y baja con BOX: antialiasing de area, sin ringing."""
    big = size * ss
    k = big / icon.size
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if rounded and icon.radius:
        draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=icon.radius * k, fill=icon.background)
    else:
        draw.rectangle([0, 0, big - 1, big - 1], fill=icon.background)

    for shape in icon.shapes:
        pts = [(x * k, y * k) for x, y in shape.points]
        if shape.fill:
            draw.polygon(pts, fill=shape.fill)
        if shape.stroke:
            w = max(1, round(shape.width * k))
            draw.line(pts, fill=shape.stroke, width=w, joint="curve")
            for x, y in (pts[0], pts[-1]):  # lineas con punta redonda
                r = w / 2
                draw.ellipse([x - r, y - r, x + r, y + r], fill=shape.stroke)

    return img.resize((size, size), Image.Resampling.BOX)


def ascii_art(img: Image.Image, width: int = 34) -> str:
    h = max(1, round(img.height * width / img.width / 2))
    small = img.resize((width, h), Image.Resampling.LANCZOS)
    rails = {
        ".": None,
        "#": (58, 125, 68),
        "@": (238, 247, 227),
        "o": (44, 106, 54),
    }
    out = []
    for y in range(h):
        row = ""
        for x in range(width):
            r, g, b, a = small.getpixel((x, y))
            if a < 40:
                row += "."
                continue
            row += min(
                rails,
                key=lambda ch: 10**9
                if rails[ch] is None
                else (r - rails[ch][0]) ** 2 + (g - rails[ch][1]) ** 2 + (b - rails[ch][2]) ** 2,
            )
        out.append(row)
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Salida
# --------------------------------------------------------------------------- #
def main() -> int:
    check_only = "--check" in sys.argv
    icon = load_svg(SVG_PATH)
    print(f"SVG: {SVG_PATH.name} | lienzo {icon.size:.0f} | fondo {icon.background[:3]} | formas {len(icon.shapes)}")

    frames = {s: render(icon, s, rounded=True) for s in (16, 32, 48)}
    apple = render(icon, 180, rounded=False).convert("RGB")

    print()
    print("== favicon 32 px ==")
    print(ascii_art(frames[32], 32))
    print()
    print("== favicon 16 px ==")
    print(ascii_art(frames[16], 16))

    if check_only:
        problems = []
        if not APPLE_PATH.exists() or not ICO_PATH.exists():
            problems.append("faltan apple-touch-icon.png o favicon.ico")
        else:
            if Image.open(APPLE_PATH).size != (180, 180):
                problems.append("apple-touch-icon.png no es 180x180")
            if Image.open(ICO_PATH).size != (48, 48):
                problems.append("favicon.ico no expone 48x48")
        if problems:
            print()
            print("DESACTUALIZADO: " + "; ".join(problems))
            return 1
        print()
        print("Los iconos existen (--check no compara bytes).")
        return 0

    apple.save(APPLE_PATH, optimize=True)
    frames[48].save(
        ICO_PATH,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[frames[16], frames[32]],
    )
    print()
    print(f"  {APPLE_PATH.name}: {APPLE_PATH.stat().st_size} bytes")
    print(f"  {ICO_PATH.name}:   {ICO_PATH.stat().st_size} bytes")

    # el ICO debe traer los tres tamanos
    ico = Image.open(ICO_PATH)
    sizes = sorted(ico.ico.sizes()) if hasattr(ico, "ico") else []
    print(f"  tamanos en el .ico: {sizes}")
    if sizes != [(16, 16), (32, 32), (48, 48)]:
        print("ERROR: el .ico no tiene los tres tamanos")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
