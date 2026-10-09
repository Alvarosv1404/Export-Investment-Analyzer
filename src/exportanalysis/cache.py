"""Cliente HTTP con cache en disco, reintentos y backoff.

Por que existe: la API publica de UN Comtrade responde 429 si se insiste, y
no es idempotente-caro repetir llamadas. Cachear en disco hace que el pipeline
sea barato de re-ejecutar y que la app web responda sin pegarle a la API.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DATA_DIR

log = logging.getLogger(__name__)

CACHE_DIR = DATA_DIR / "raw" / "_cache"


def _cache_path(url: str, namespace: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:20]
    folder = CACHE_DIR / namespace
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}.json"


def build_session(retries: int = 5, backoff: float = 1.5) -> requests.Session:
    """Session con retry automatico para 429 y 5xx."""
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        backoff_factor=backoff,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": "exportanalysis/0.1 (analisis de inversion; contacto: config)",
            "Accept": "application/json",
        }
    )
    return session


def fetch_json(
    url: str,
    *,
    namespace: str,
    session: requests.Session | None = None,
    sleep: float = 0.0,
    use_cache: bool = True,
    max_age_hours: int | None = None,
) -> dict[str, Any]:
    """GET a una API que devuelve JSON, con cache en disco.

    max_age_hours: si se indica, una entrada mas vieja se vuelve a pedir.
    Sin esto, la cache es permanente (util para datos historicos que no cambian).
    """
    path = _cache_path(url, namespace)

    if use_cache and path.exists():
        if max_age_hours is None or (time.time() - path.stat().st_mtime) < max_age_hours * 3600:
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
        log.info("Cache vencido (%s), refetch", path.name)

    session = session or build_session()
    if sleep:
        time.sleep(sleep)

    log.info("GET %s", url)
    response = session.get(url, timeout=90)
    response.raise_for_status()
    payload = response.json()

    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    tmp.replace(path)
    return payload
