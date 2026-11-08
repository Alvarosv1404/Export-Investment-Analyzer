"""Cliente HTTP para Turso (libSQL distribuido).

Usa httpx (ya dependencia del proyecto) para llamar a la API HTTP de Turso,
sin extensiones nativas. Compatible con Vercel Functions y cualquier entorno
serverless que no admita SQLite nativo.

Uso:
    client = TursoClient()
    df = client.query_df("SELECT * FROM peru_exports_ts WHERE hs6 = ?", ["070920"])

Variables de entorno requeridas (en Vercel y en local si se usa Turso):
    TURSO_DATABASE_URL  — URL de la base, formato: libsql://<nombre>-<org>.turso.io
    TURSO_AUTH_TOKEN    — Token de autenticación generado en turso.io
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd


def _turso_configured() -> bool:
    """True si las variables de Turso están definidas en el entorno."""
    return bool(os.getenv("TURSO_DATABASE_URL") and os.getenv("TURSO_AUTH_TOKEN"))


class TursoClient:
    """Cliente síncrono para la API HTTP pipeline de Turso.

    Se instancia una vez por proceso (singleton en turso_client()) y se
    reutiliza: httpx.Client mantiene una conexión persistente con el servidor
    de Turso, lo que elimina el handshake TLS en cada query.
    """

    def __init__(self) -> None:
        url = os.environ["TURSO_DATABASE_URL"]
        self._token = os.environ["TURSO_AUTH_TOKEN"]
        # La API HTTP de Turso acepta https://; los clientes libsql usan libsql://
        base = url.replace("libsql://", "https://").rstrip("/")
        self._endpoint = f"{base}/v2/pipeline"
        self._http = httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: list[Any] | None = None) -> dict:
        """Ejecuta una sentencia SQL y devuelve la respuesta cruda de Turso."""
        args = self._encode_args(params or [])
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": args}},
                {"type": "close"},
            ]
        }
        resp = self._http.post(
            self._endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        result = data["results"][0]
        if result["type"] == "error":
            raise RuntimeError(f"Turso error: {result['error']['message']}")
        return result["response"]["result"]

    def query_df(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        """Ejecuta una SELECT y devuelve un DataFrame de pandas.

        Los valores NULL de Turso se convierten a None; pandas los transforma
        automáticamente en NaN para columnas numéricas.
        """
        result = self.execute(sql, params)
        cols = [c["name"] for c in result["cols"]]
        rows = [
            [cell.get("value") for cell in row]
            for row in result["rows"]
        ]
        return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_args(params: list[Any]) -> list[dict]:
        """Convierte parámetros Python al formato de args de Turso."""
        encoded = []
        for p in params:
            if p is None:
                encoded.append({"type": "null"})
            elif isinstance(p, bool):
                encoded.append({"type": "integer", "value": str(int(p))})
            elif isinstance(p, int):
                encoded.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                encoded.append({"type": "float", "value": str(p)})
            else:
                encoded.append({"type": "text", "value": str(p)})
        return encoded


# Singleton: una sola instancia por proceso, se crea la primera vez que se pide.
_client: TursoClient | None = None


def turso_client() -> TursoClient:
    """Devuelve el cliente Turso singleton.

    Lanza RuntimeError si las variables de entorno no están configuradas.
    Usa _turso_configured() antes de llamar aquí si Turso es opcional.
    """
    global _client
    if _client is None:
        _client = TursoClient()
    return _client
