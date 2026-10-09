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

import { getAnalysis, getProducts } from './api.js'
import { renderAll } from './charts.js'
import {
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

const state = {
  slug: new URLSearchParams(location.search).get('slug'),
  targetShare: new URLSearchParams(location.search).get('target_share') || '',
  products: [],
}

/** Actualiza la URL sin recargar, para que la vista sea compartible. */
function syncURL() {
  const params = new URLSearchParams()
  if (state.slug) params.set('slug', state.slug)
  if (state.targetShare) params.set('target_share', state.targetShare)
  const qs = params.toString()
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname)
}

function showError(message) {
  document.getElementById('app').innerHTML = `
    <div class="alert error"><strong>Error:</strong> ${escapeHTML(message)}</div>`
}

/** Selector de producto y campo de participacion objetivo. */
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

  const shareInput = `
    <form class="share-form" id="shareForm">
      <label for="shareInput">Participacion de mercado objetivo (opcional)</label>
      <div class="share-controls">
        <input type="number" id="shareInput" name="target_share" min="0" max="100" step="0.5"
               placeholder="auto" value="${escapeHTML(shareInputValue())}" />
        <span class="share-hint">% &mdash; vacio = share actual + 2 pp</span>
        <button type="submit" class="btn">Aplicar</button>
      </div>
    </form>`

  return `<nav class="products">${chips}</nav>${shareInput}`
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
  return `?${params.toString()}`
}

/** Inserta un control de participacion que dispara una recarga suave. */
function bindShareForm(onChange) {
  const form = document.getElementById('shareForm')
  if (!form) return
  form.addEventListener('submit', (event) => {
    event.preventDefault()
    const raw = document.getElementById('shareInput').value.trim()
    // El input esta en porcentaje (0-100); la API espera fraccion (0-1).
    state.targetShare = raw === '' ? '' : (Number(raw) / 100).toFixed(4)
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
    sources(result),
  ].join('')

  renderAll(result)
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
    const result = await getAnalysis(state.slug, state.targetShare)
    document.getElementById('controls').innerHTML = renderControls()
    bindShareForm(load)
    render(result)
  } catch (err) {
    showError(err.message)
  }
}

document.addEventListener('DOMContentLoaded', load)
