/**
 * Consulta de datos a la API.
 *
 * Toda llamada a /api pasa por acá. El motivo es concreto: en desarrollo el
 * frontend corre en :5173 y el backend en :8000, pero el proxy de Vite hace que
 * el navegador solo vea un origen. Si alguien despliega el build estatico
 * servido por FastAPI, la misma ruta relativa funciona sin cambiar nada.
 *
 * Por eso NO hay URLs absolutas ni puerto hardcodeado en ningun modulo.
 */

const BASE = ''

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch {
      /* la respuesta no era JSON: nos quedamos con el status */
    }
    throw new Error(detail)
  }
  return res.json()
}

export const getProducts = () => getJSON('/api/products')
export const getAnalysis = (slug, targetShare) => {
  const q = targetShare === null || targetShare === undefined || targetShare === ''
    ? ''
    : `?target_share=${encodeURIComponent(targetShare)}`
  return getJSON(`/api/analysis/${encodeURIComponent(slug)}${q}`)
}
export const getHealth = () => getJSON('/health')
