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

export const getAnalysis = (slug, targetShareOrOpts, priceArg) => {
  const params = new URLSearchParams()
  if (typeof targetShareOrOpts === 'object' && targetShareOrOpts !== null) {
    const opts = targetShareOrOpts
    if (opts.targetShare !== undefined && opts.targetShare !== '') params.set('target_share', opts.targetShare)
    if (opts.price !== undefined && opts.price !== '') params.set('price_usd_per_kg', opts.price)
    if (opts.capacity !== undefined && opts.capacity !== '') params.set('capacity_kg_year', opts.capacity)
    if (opts.year1Volume !== undefined && opts.year1Volume !== '') {
      const volTons = parseFloat(opts.year1Volume)
      const volKg = !isNaN(volTons) && volTons > 0 ? volTons * 1000 : opts.year1Volume
      params.set('year1_volume_kg', volKg)
    }
    if (opts.annualGrowth !== undefined && opts.annualGrowth !== '') params.set('annual_volume_growth_pct', opts.annualGrowth)
    if (opts.purchaseCost !== undefined && opts.purchaseCost !== '') params.set('purchase_cost_usd_per_kg', opts.purchaseCost)
    if (opts.variableCost !== undefined && opts.variableCost !== '') params.set('variable_cost_usd_per_kg', opts.variableCost)
    if (opts.capex !== undefined && opts.capex !== '') params.set('capex_usd', opts.capex)
    if (opts.opex !== undefined && opts.opex !== '') params.set('opex_fixed_usd_year', opts.opex)
    if (opts.workingCapital !== undefined && opts.workingCapital !== '') params.set('working_capital_usd', opts.workingCapital)
    if (opts.discountRate !== undefined && opts.discountRate !== '') params.set('discount_rate', opts.discountRate)
    if (opts.priceVolatility !== undefined && opts.priceVolatility !== '') params.set('price_volatility_pct', opts.priceVolatility)
    if (opts.purchaseCostVolatility !== undefined && opts.purchaseCostVolatility !== '') params.set('purchase_cost_volatility_pct', opts.purchaseCostVolatility)
    if (opts.volumeVolatility !== undefined && opts.volumeVolatility !== '') params.set('volume_volatility_pct', opts.volumeVolatility)
    if (opts.projectionMethod !== undefined && opts.projectionMethod !== '') params.set('projection_method', opts.projectionMethod)
  } else {
    if (targetShareOrOpts !== null && targetShareOrOpts !== undefined && targetShareOrOpts !== '') {
      params.set('target_share', targetShareOrOpts)
    }
    if (priceArg !== null && priceArg !== undefined && priceArg !== '') {
      params.set('price_usd_per_kg', priceArg)
    }
  }
  const q = params.toString()
  return getJSON(`/api/analysis/${encodeURIComponent(slug)}${q ? `?${q}` : ''}`)
}

export const getExportUrl = (slug, opts = {}) => {
  const params = new URLSearchParams()
  const set = (key, value) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value)
  }
  set('target_share', opts.targetShare)
  set('price_usd_per_kg', opts.price)
  set('capacity_kg_year', opts.capacity)
  if (opts.year1Volume !== undefined && opts.year1Volume !== '') {
    const volTons = parseFloat(opts.year1Volume)
    const volKg = !isNaN(volTons) && volTons > 0 ? volTons * 1000 : opts.year1Volume
    set('year1_volume_kg', volKg)
  }
  set('annual_volume_growth_pct', opts.annualGrowth)
  set('purchase_cost_usd_per_kg', opts.purchaseCost)
  set('variable_cost_usd_per_kg', opts.variableCost)
  set('capex_usd', opts.capex)
  set('opex_fixed_usd_year', opts.opex)
  set('working_capital_usd', opts.workingCapital)
  set('discount_rate', opts.discountRate)
  set('price_volatility_pct', opts.priceVolatility)
  set('purchase_cost_volatility_pct', opts.purchaseCostVolatility)
  set('volume_volatility_pct', opts.volumeVolatility)
  set('projection_method', opts.projectionMethod)
  const q = params.toString()
  return `/api/analysis/${encodeURIComponent(slug)}/export/excel${q ? `?${q}` : ''}`
}
export const getComparison = (slugs = []) => {
  const q = slugs.length ? `?slugs=${encodeURIComponent(slugs.join(','))}` : ''
  return getJSON(`/api/comparison${q}`)
}
export const getRanking = (slugs = []) => {
  const q = slugs.length ? `?slugs=${encodeURIComponent(slugs.join(','))}` : ''
  return getJSON(`/api/ranking${q}`)
}
export const getHealth = () => getJSON('/health')
