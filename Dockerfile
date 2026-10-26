# syntax=docker/dockerfile:1

# Imagen multi-etapa para el monolito: Vite compila la UI y FastAPI la sirve
# junto con la API desde el mismo origen (sin CORS, un solo puerto).
#
# Ojo con `pip install -e .`:
#   config.py ubica config/ y data/ subiendo desde src/, y api/main.py ubica
#   dist/ con parents[3]. Esas rutas solo existen si el paquete se importa
#   desde /app/src. Con una instalacion normal (a site-packages) la app no
#   encontraria ni config/, ni data/, ni dist/. Por eso se instala en modo
#   editable, igual que hace render.yaml.

# Versiones fijas: tag de parche exacto (no `22-alpine` a secas) para que un
# rebuild no cambie Node/Python por detras. Las de Python ademas estan en
# constraints.txt; las de Node, en package-lock.json (via `npm ci`).

# ---------- Etapa 1: build del frontend ----------
FROM node:22.23.4-alpine AS frontend

WORKDIR /build

# `npm ci` es reproducible: respeta package-lock.json.
COPY package.json package-lock.json ./
RUN npm ci

# vite.config.js lee dev.config.json al cargar la config, incluso en build.
# Sin ese archivo `npm run build` falla, asi que se copia aqui y NO se excluye
# en .dockerignore.
COPY vite.config.js dev.config.json ./
COPY frontend ./frontend
RUN npm run build

# ---------- Etapa 2: runtime (Python) ----------
FROM python:3.12.15-slim AS runtime

# 3.12 y no 3.14: pyproject pide >=3.11 y en 3.12 hay wheels estables de
# pandas/numpy/pyarrow. Es tambien la version que usa render.yaml.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROJECT_ROOT=/app

WORKDIR /app

# Capa cacheable: primero la metadata y un paquete vacio, para instalar las
# dependencias sin depender del codigo. Asi, cambiar src/ no reinstala pandas.
#
# constraints.txt fija las versiones exactas que se validaron. Sin el, `pip`
# resolvia los rangos de pyproject.toml (pandas>=2.2) y un build podia traer
# pandas 3.1, que rompia la API. pip/setuptools/wheel tambien van con version
# exacta para que la imagen sea reproducible.
COPY pyproject.toml constraints.txt ./
RUN pip install "pip==26.2.2" "setuptools==84.2.1" "wheel==0.48.0" \
 && mkdir -p src/exportanalysis \
 && : > src/exportanalysis/__init__.py \
 && pip install -e . -c constraints.txt

# Codigo real: reemplaza el paquete vacio. El enlace editable ya apunta a
# /app/src, asi que no hace falta reinstalar.
COPY src ./src

# Configuracion y datos que la app lee en caliente (YAML + Excel de Trade Map).
COPY config ./config
COPY data ./data

# UI ya compilada por la etapa de Node.
COPY --from=frontend /build/dist ./dist

# Usuario sin privilegios: el proceso solo necesita leer.
RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Respeta $PORT (Render, Railway, Fly) y cae a 8000 en local.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','8000'), timeout=3).status == 200 else 1)"

CMD ["sh", "-c", "exec uvicorn exportanalysis.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
