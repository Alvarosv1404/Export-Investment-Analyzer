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
import { destroyCharts, renderAll, renderComparisonCharts } from './charts.js'
import {
  comparison,
  competitors,
  destinations,
  headroom,
  investment,
  market,
  sensitivity,
  sources,
  sunatPrice,
  tariffs,
  unitEconomics,
} from './components.js'
import { escapeHTML } from './components.js'

const urlParams = new URLSearchParams(location.search)
const state = {
  slug: urlParams.get('slug'),
  targetShare: urlParams.get('target_share') || '',
  price: urlParams.get('price') || '',
  view: urlParams.get('view') === 'compare' || urlParams.get('compare') === '1' ? 'compare' : 'analysis',
  compareSlugs: (urlParams.get('compare_slugs') || '').split(',').filter(Boolean),
  products: [],
  comparisonData: null,
}

/** Actualiza la URL sin recargar, para que la vista sea compartible. */
function syncURL() {
  const params = new URLSearchParams()
  if (state.slug) params.set('slug', state.slug)
  if (state.targetShare) params.set('target_share', state.targetShare)
  if (state.price) params.set('price', state.price)
  if (state.view === 'compare') {
    params.set('view', 'compare')
    if (state.compareSlugs.length) params.set('compare_slugs', state.compareSlugs.join(','))
  }
  const qs = params.toString()
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname)
}

function showError(message) {
  document.getElementById('app').innerHTML = `
    <div class="alert error"><strong>Error:</strong> ${escapeHTML(message)}</div>`
}

/** Controles para analisis individual o comparacion de productos. */
function renderControls() {
  const tabs = `
    <nav class="view-tabs" aria-label="Tipo de analisis">
      <button type="button" class="view-tab ${state.view === 'analysis' ? 'active' : ''}" data-view="analysis">
        Analisis por producto
      </button>
      <button type="button" class="view-tab ${state.view === 'compare' ? 'active' : ''}" data-view="compare">
        Comparacion de productos
      </button>
    </nav>`
  if (state.view === 'compare') {
    return `${tabs}
      <form class="controls-form comparison-controls" id="comparisonForm">
        <fieldset class="compare-picker">
          <legend>Elige los productos que quieres comparar</legend>
          <p class="compare-picker-hint">Marca uno o varios. Puedes empezar con el producto actual y añadir otros.</p>
          <label class="compare-search-label" for="compareSearch">Buscar por nombre o código HS</label>
          <input type="search" id="compareSearch" class="compare-search" placeholder="Ej.: café o 090111" />
          <div class="compare-options">
            ${state.products
              .map(
                (p) => `
                  <label class="compare-option" data-product-name="${escapeHTML(`${p.name} ${p.hs6}`.toLowerCase())}">
                    <input type="checkbox" name="compareSlugs" value="${escapeHTML(p.slug)}"
                           ${state.compareSlugs.includes(p.slug) ? 'checked' : ''} />
                    <span class="compare-option-copy">
                      <span class="compare-option-name">${escapeHTML(p.name)}</span>
                      <span class="hs6">HS ${escapeHTML(p.hs6)}</span>
                    </span>
                  </label>`
              )
              .join('')}
          </div>
          <div class="compare-picker-footer">
            <span class="compare-selection-count" aria-live="polite"></span>
            <div class="compare-picker-actions">
              <button type="button" class="text-btn" id="selectAllProducts">Seleccionar todos</button>
              <button type="button" class="text-btn" id="clearProducts">Limpiar</button>
            </div>
          </div>
        </fieldset>
        <div class="comparison-submit">
          <button type="submit" class="btn">Ver comparacion</button>
        </div>
      </form>`
  }

  const form = `
    <form class="controls-form" id="controlsForm">
      <div class="control-block">
        <label for="productSelect">Producto para analizar</label>
        <select id="productSelect" name="slug">
          ${state.products
            .map(
              (p) => `
                <option value="${escapeHTML(p.slug)}" ${p.slug === state.slug ? 'selected' : ''}>
                  ${escapeHTML(p.name)} (HS ${escapeHTML(p.hs6)})
                </option>`
            )
            .join('')}
        </select>
      </div>
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
      <button type="submit" class="btn">Aplicar</button>
    </form>`

  return `${tabs}${form}`
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

/** Inserta los controles que disparan una recarga suave. */
function bindControls(onChange) {
  document.querySelectorAll('.view-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      state.view = tab.dataset.view
      syncURL()
      onChange()
    })
  })

  const comparisonForm = document.getElementById('comparisonForm')
  if (comparisonForm) {
    const checkboxes = Array.from(comparisonForm.querySelectorAll('input[name="compareSlugs"]'))
    const updateSelectionCount = () => {
      const selectedCount = checkboxes.filter((input) => input.checked).length
      comparisonForm.querySelector('.compare-selection-count').textContent =
        `${selectedCount} producto${selectedCount === 1 ? '' : 's'} seleccionado${selectedCount === 1 ? '' : 's'}`
    }
    checkboxes.forEach((input) => input.addEventListener('change', updateSelectionCount))
    document.getElementById('selectAllProducts').addEventListener('click', () => {
      checkboxes.forEach((input) => {
        const option = input.closest('.compare-option')
        if (option && option.hidden) return
        input.checked = true
      })
      updateSelectionCount()
    })
    document.getElementById('clearProducts').addEventListener('click', () => {
      checkboxes.forEach((input) => {
        input.checked = false
      })
      updateSelectionCount()
    })
    document.getElementById('compareSearch').addEventListener('input', (event) => {
      const query = event.target.value.trim().toLowerCase()
      comparisonForm.querySelectorAll('.compare-option').forEach((option) => {
        option.hidden = !option.dataset.productName.includes(query)
      })
    })
    updateSelectionCount()

    comparisonForm.addEventListener('submit', (event) => {
      event.preventDefault()
      state.compareSlugs = Array.from(
        comparisonForm.querySelectorAll('input[name="compareSlugs"]:checked')
      ).map((input) => input.value)
      if (!state.compareSlugs.length) {
        document.getElementById('app').innerHTML =
          '<div class="alert warn">Selecciona al menos un producto para mostrar la comparacion.</div>'
        return
      }
      syncURL()
      onChange()
    })
    return
  }

  const form = document.getElementById('controlsForm')
  if (!form) return
  document.getElementById('productSelect').addEventListener('change', (event) => {
    state.slug = event.target.value
    syncURL()
    onChange()
  })
  form.addEventListener('submit', (event) => {
    event.preventDefault()
    const share = document.getElementById('shareInput').value.trim()
    const price = document.getElementById('priceInput').value.trim()
    // El input esta en porcentaje (0-100); la API espera fraccion (0-1).
    state.targetShare = share === '' ? '' : (Number(share) / 100).toFixed(4)
    state.price = price === '' ? '' : String(Number(price))
    syncURL()
    onChange()
  })
}

function render(result) {
  const app = document.getElementById('app')
  destroyCharts()

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
    sunatPrice(result),
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

function renderComparisonView() {
  destroyCharts()
  const app = document.getElementById('app')
  app.innerHTML = comparison(state.comparisonData)
  renderComparisonCharts(state.comparisonData)
}

async function load() {
  const reqId = ++load.reqId
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

  document.getElementById('controls').innerHTML = renderControls()
  bindControls(load)

  if (state.view === 'compare') {
    if (!state.compareSlugs.length) {
      document.getElementById('app').innerHTML = `
        <div class="alert">
          Aun no hay productos seleccionados. Marca uno o varios en el panel de arriba
          y pulsa <b>Ver comparacion</b> para ver el crecimiento interanual y el CAGR
          desde la base (2016, o el primer anio en que el producto exporto).
        </div>`
      return
    }
    try {
      state.comparisonData = await getComparison(state.compareSlugs)
      if (reqId !== load.reqId) return
      renderComparisonView()
    } catch (err) {
      showError(err.message)
    }
    return
  }

  try {
    const result = await getAnalysis(state.slug, state.targetShare, state.price)
    if (reqId !== load.reqId) return
    render(result)
  } catch (err) {
    showError(err.message)
  }
}

load.reqId = 0
