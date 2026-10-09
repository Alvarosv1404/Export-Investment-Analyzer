/**
 * Punto de entrada del frontend.
 *
 * El flujo es: leer el slug de la URL -> pedir el catalogo y el analisis ->
 * renderizar los ocho bloques -> dibujar los graficos. Todo el estado vive en
 * la URL (slug y target_share), asi que cualquier vista es compartible con un
 * link y el boton de atras del navegador funciona sin logica extra.
 *
 * En desarrollo Vite sirve este archivo y hace proxy de /api hacia FastAPI.
 * En produccion, el mismo build lo sirve FastAPI desde el mismo origen.
 */

import { getAnalysis, getComparison, getProducts } from './api.js'
import { renderAll } from './charts.js'
import {
  comparison,
  competitors,
  destinations,
  headroom,
  investment,
  market,
  sensitivity,
  sources,
  tariffs,
  unitEconomics,
} from './components.js'
import { escapeHTML } from './components.js'

const urlParams = new URLSearchParams(location.search)
const state = {
  slug: urlParams.get('slug'),
  targetShare: urlParams.get('target_share') || '',
  price: urlParams.get('price') || '',
  compare: urlParams.get('compare') === '1',
  products: [],
  comparisonData: null,
}

/** Actualiza la URL sin recargar, para que la vista sea compartible. */
function syncURL() {
  const params = new URLSearchParams()
  if (state.slug) params.set('slug', state.slug)
  if (state.targetShare) params.set('target_share', state.targetShare)
  if (state.price) params.set('price', state.price)
  if (state.compare) params.set('compare', '1')
  const qs = params.toString()
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname)
}

function showError(message) {
  document.getElementById('app').innerHTML = `
    <div class="alert error"><strong>Error:</strong> ${escapeHTML(message)}</div>`
}

/** Selector de producto, participacion objetivo, precio y comparacion. */
function renderControls() {
  const chips = state.products
    .map(
      (p) => `
      <a class="chip ${p.slug === state.slug ? 'active' : ''}" href="${escapeHTML(productHref(p.slug))}"
         data-slug="${escapeHTML(p.slug)}">
        ${escapeHTML(p.name)} <span class="hs6">HS ${escapeHTML(p.hs6)}</span>
      </a>`
    )
    .join('')

  const form = `
    <form class="controls-form" id="controlsForm">
      <div class="control-block">
        <label for="shareInput">Participacion de mercado objetivo (opcional)</label>
        <div class="share-controls">
          <input type="number" id="shareInput" name="target_share" min="0" max="100" step="0.5"
                 placeholder="auto" value="${escapeHTML(shareInputValue())}" />
          <span class="share-hint">% &mdash; vacio = share actual + 2 pp</span>
        </div>
      </div>
      <div class="control-block">
        <label for="priceInput">Precio FOB de venta (opcional)</label>
        <div class="share-controls">
          <input type="number" id="priceInput" name="price" min="0" step="0.001"
                 placeholder="auto" value="${escapeHTML(state.price)}" />
          <span class="share-hint">USD/kg &mdash; vacio = calculado de los historicos</span>
        </div>
      </div>
      <label class="check">
        <input type="checkbox" id="compareInput" ${state.compare ? 'checked' : ''} />
        Comparar con los demas productos del catalogo
      </label>
      <button type="submit" class="btn">Aplicar</button>
    </form>`

  return `<nav class="products">${chips}</nav>${form}`
}

/**
 * La URL y la API trabajan en fraccion (0.12); el input trabaja en porcentaje
 * (12). Sin esta conversion, abrir un link con `?target_share=0.12` muestra
 * "0.12 %" en el input y al pulsar Aplicar manda 0.0012.
 */
function shareInputValue() {
  if (state.targetShare === '') return ''
  const percent = Number(state.targetShare) * 100
  if (!Number.isFinite(percent)) return ''
  return String(Math.round(percent * 100) / 100)
}

/** Mantiene la participacion elegida al cambiar de producto. */
function productHref(slug) {
  const params = new URLSearchParams({ slug })
  if (state.targetShare) params.set('target_share', state.targetShare)
  if (state.price) params.set('price', state.price)
  if (state.compare) params.set('compare', '1')
  return `?${params.toString()}`
}

/** Inserta los controles que disparan una recarga suave. */
function bindControls(onChange) {
  const form = document.getElementById('controlsForm')
  if (!form) return
  form.addEventListener('submit', (event) => {
    event.preventDefault()
    const share = document.getElementById('shareInput').value.trim()
    const price = document.getElementById('priceInput').value.trim()
    // El input esta en porcentaje (0-100); la API espera fraccion (0-1).
    state.targetShare = share === '' ? '' : (Number(share) / 100).toFixed(4)
    state.price = price === '' ? '' : String(Number(price))
    state.compare = document.getElementById('compareInput').checked
    syncURL()
    onChange()
  })
}

function render(result) {
  const app = document.getElementById('app')

  if (result.error || (result.market && !result.market.available)) {
    showError(result.error || result.market?.message || 'Sin datos.')
    return
  }

  const product = result.product || {}
  const meta = `
    <section class="card">
      <h2>${escapeHTML(product.name || '')}</h2>
      <div class="meta">
        <span>HS-6 <b>${escapeHTML(product.hs6 || '')}</b></span>
        ${product.nandina ? `<span>Partida SUNAT <b>${escapeHTML(product.nandina)}</b></span>` : ''}
        <span>Ultimo anio con data <b>${result.market.latest_year}</b></span>
      </div>
    </section>`

  app.innerHTML = [
    meta,
    unitEconomics(result.unit_economics),
    market(result.market),
    destinations(result.destinations),
    competitors(result.competitors),
    headroom(result.headroom),
    tariffs(result),
    investment(result.investment),
    sensitivity(result.investment),
    state.compare ? comparison(state.comparisonData) : '',
    sources(result),
  ].join('')

  renderAll(result, state.comparisonData)
}

async function load() {
  syncURL()

  // El catalogo se pide siempre, no solo cuando la URL no trae slug: si no,
  // el selector muestra un unico producto y no hay forma de cambiar de producto
  // sin editar la URL a mano.
  if (!state.products.length) {
    document.getElementById('app').innerHTML = '<div class="alert">Cargando productos...</div>'
    try {
      const data = await getProducts()
      state.products = data.products
    } catch (err) {
      showError(err.message)
      return
    }
  }

  if (!state.slug && state.products.length) {
    state.slug = state.products[0].slug
    syncURL()
  }

  try {
    const result = await getAnalysis(state.slug, state.targetShare, state.price)
    state.comparisonData = null
    if (state.compare) {
      try {
        state.comparisonData = await getComparison([])
      } catch (err) {
        state.comparisonData = { error: err.message }
      }
    }
    document.getElementById('controls').innerHTML = renderControls()
    bindControls(load)
    render(result)
  } catch (err) {
    showError(err.message)
  }
}

document.addEventListener('DOMContentLoaded', load)
