"""Entry point de Vercel: importa la app FastAPI y la expone como handler ASGI.

Vercel detecta automáticamente las apps ASGI/WSGI en api/*.py.
La app lee config/ con rutas relativas al paquete, que Vercel incluye
en el bundle de la función junto con src/ y config/.
"""
import sys
from pathlib import Path

# Añade src/ al path para que `import exportanalysis` funcione en Vercel.
# En local el paquete se instala con `pip install -e .`; en Vercel no hay
# editable-install, así que se resuelve añadiendo src/ explícitamente.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from exportanalysis.api.main import app  # noqa: E402  (import después de sys.path)

# Vercel busca una variable llamada `app` (ASGI) o `handler` (WSGI).
__all__ = ["app"]
