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

import { getAnalysis, getComparison, getExportUrl, getProducts, getRanking } from './api.js'
import {
  destroyCharts,
  projectionChart,
  renderFinancialCharts,
  renderAll,
  renderComparisonCharts,
  renderRankingChart,
  shareDonut,
} from './charts.js'
import {
  comparison,
  competitors,
  destinations,
  headroom,
  investment,
  market,
  marketShare,
  missingAssumptions,
  projection,
  ranking,
  sensitivity,
  monteCarloRisk,
  simulatorPanel,
  sources,
  sunatPrice,
  unitEconomics,
} from './components.js'
import { escapeHTML } from './components.js'

const urlParams = new URLSearchParams(location.search)
const hasSavedFinancialInputs = urlParams.get('evaluation_inputs') === '1'
const initialFinancialValue = (param) =>
  hasSavedFinancialInputs ? (urlParams.get(param) || '') : ''
const state = {
  slug: urlParams.get('slug'),
  // Año del gráfico circular de participación de mercado. Vive en la URL.
  shareYear: urlParams.get('share_year') ? Number(urlParams.get('share_year')) : null,
  // Método de proyección para el gráfico de exportación. Vive en la URL.
  projectionMethod: urlParams.get('projection_method') || 'moving_average',
  capex: initialFinancialValue('capex'),
  variableCost: initialFinancialValue('variable_cost'),
  year1Volume: initialFinancialValue('year1_volume'),
  annualGrowth: initialFinancialValue('annual_growth'),
  opex: initialFinancialValue('opex'),
  // COK se maneja en porcentaje (12); la API espera fracción (0.12).
  discountRate: initialFinancialValue('wacc'),
  view: urlParams.get('view') === 'compare' || urlParams.get('compare') === '1' ? 'compare' : 'analysis',
  compareSlugs: (urlParams.get('compare_slugs') || '').split(',').filter(Boolean),
  products: [],
  comparisonData: null,
  rankingData: null,
}

/** Actualiza la URL sin recargar, para que la vista sea compartible. */
function syncURL() {
  const params = new URLSearchParams()
  const set = (key, value) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value)
  }
  if (state.slug) params.set('slug', state.slug)
  if (state.shareYear) params.set('share_year', state.shareYear)
  if (state.projectionMethod) params.set('projection_method', state.projectionMethod)
  set('year1_volume', state.year1Volume)
  set('annual_growth', state.annualGrowth)
  set('variable_cost', state.variableCost)
  set('capex', state.capex)
  set('opex', state.opex)
  set('wacc', state.discountRate)
  if ([state.year1Volume, state.annualGrowth, state.variableCost, state.capex, state.opex, state.discountRate]
    .some((value) => value !== '')) {
    params.set('evaluation_inputs', '1')
  }
  if (state.view === 'compare') {
    params.set('view', 'compare')
    if (state.compareSlugs.length) params.set('compare_slugs', state.compareSlugs.join(','))
  }
  const qs = params.toString()
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname)
}

/**
 * Opciones de análisis a partir del estado (simulador + controles superiores).
 * Un solo lugar traduce el estado del frontend a los query params de la API,
 * para que la carga inicial y el simulador hablen con el mismo contrato.
 */
function analysisOpts() {
  const waccFraction =
    state.discountRate !== '' ? (Number(state.discountRate) / 100).toFixed(4) : ''
  return {
    year1Volume: state.year1Volume,
    annualGrowth: state.annualGrowth,
    variableCost: state.variableCost,
    capex: state.capex,
    opex: state.opex,
    discountRate: waccFraction,
    projectionMethod: state.projectionMethod,
  }
}

function showError(message) {
  document.getElementById('app').innerHTML = `
    <div class="alert error"><strong>Error:</strong> ${escapeHTML(message)}</div>`
}

/** Mensaje de la vista de comparación cuando aún no hay productos marcados. */
const EMPTY_COMPARISON = `
  <div class="alert comparison-empty">
    <div class="comparison-empty-icon">📊</div>
    <strong>Sin productos seleccionados</strong>
    <p>Marca uno o varios productos en el panel <strong>"Elige los productos que quieres comparar"</strong> de arriba.<br>
    La comparación y el ranking se actualizan automáticamente.</p>
  </div>`

/**
 * Relee la comparacion al cambiar la seleccion sin volver a pintar los controles.
 * Asi el buscador conserva el texto y el foco, y solo se refresca la data. El
 * guard con `load.reqId` descarta respuestas que llegan fuera de orden.
 */
async function refreshComparison() {
  const form = document.getElementById('comparisonForm')
  if (!form) return

  state.compareSlugs = Array.from(
    form.querySelectorAll('input[name="compareSlugs"]:checked')
  ).map((input) => input.value)
  syncURL()

  const reqId = ++load.reqId
  if (!state.compareSlugs.length) {
    state.comparisonData = null
    state.rankingData = null
    renderComparisonView()
    return
  }
  try {
    const [data, rank] = await Promise.all([
      getComparison(state.compareSlugs),
      getRanking(state.compareSlugs),
    ])
    if (reqId !== load.reqId) return
    state.comparisonData = data
    state.rankingData = rank
    renderComparisonView()
  } catch (err) {
    showError(err.message)
  }
}

/** Genera las opciones para el custom select (con role="option" y atributos necesarios). */
function productOptionsForCustomSelect() {
  const option = (p, idx) =>
    `<div role="option" id="opt-${idx}" data-value="${escapeHTML(p.slug)}" data-industry="${escapeHTML(p.industry || '')}" aria-selected="${p.slug === state.slug}">${escapeHTML(p.name)}</div>`
  return state.products.map(option).join('')
}

/** Genera las opciones para el select nativo (fallback/form submission). */
function productOptionsForNativeSelect() {
  const option = (p) =>
    `<option value="${escapeHTML(p.slug)}" ${p.slug === state.slug ? 'selected' : ''} data-industry="${escapeHTML(p.industry || '')}">${escapeHTML(p.name)}</option>`
  return state.products.map(option).join('')
}

/** Genera el HTML del custom select para la vista de análisis. */
function renderCustomSelect() {
  const selected = state.products.find(p => p.slug === state.slug) || state.products[0]
  const selectedLabel = selected ? selected.name : 'Seleccionar producto'
  const customOptionsHtml = productOptionsForCustomSelect()
  const nativeOptionsHtml = productOptionsForNativeSelect()
  const showSearch = state.products.length > 20

  return `
    <div class="custom-select" id="customSelect" role="combobox" aria-expanded="false" aria-haspopup="listbox" aria-label="Producto para analizar">
      <label class="custom-select-label" for="customSelectTrigger">Producto para analizar</label>
      <div class="custom-select-trigger" id="customSelectTrigger" tabindex="0" role="button" aria-haspopup="listbox" aria-expanded="false">
        <span class="custom-select-value">${escapeHTML(selectedLabel)}</span>
        <svg class="custom-select-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="6 9 12 15 18 9"></polyline></svg>
      </div>
      <div class="custom-select-dropdown" id="customSelectDropdown" role="listbox" hidden>
        ${showSearch ? `
        <div class="custom-select-search-wrapper">
          <input type="search" class="custom-select-search" placeholder="Buscar producto..." aria-label="Buscar en la lista" autocomplete="off">
        </div>` : ''}
        <div class="custom-select-options" id="customSelectOptions" role="listbox">
          ${customOptionsHtml}
        </div>
      </div>
      <!-- Hidden native select for form submission / SSR fallback -->
      <select id="productSelect" name="slug" class="custom-select-native" hidden>
        ${nativeOptionsHtml}
      </select>
    </div>`
}

/** Controles para analisis individual o comparacion de productos. */
function renderControls() {
  const tabs = `
    <nav class="view-tabs" aria-label="Tipo de análisis">
      <button type="button" class="view-tab ${state.view === 'analysis' ? 'active' : ''}" data-view="analysis">
        Análisis por producto
      </button>
      <button type="button" class="view-tab ${state.view === 'compare' ? 'active' : ''}" data-view="compare">
        Comparación de productos
      </button>
    </nav>`
  if (state.view === 'compare') {
    const industries = [...new Set(state.products.map((p) => p.industry).filter(Boolean))].sort()
    const industryFilter = industries.length
      ? `
          <div class="filter-chips" id="compareIndustryChips" role="group" aria-label="Filtrar por industria">
            <button type="button" class="filter-chip active" data-industry="">Todas</button>
            ${industries.map((name) => `<button type="button" class="filter-chip" data-industry="${escapeHTML(name)}">${escapeHTML(name)}</button>`).join('')}
          </div>`
      : ''
    return `${tabs}
      <form class="controls-form comparison-controls" id="comparisonForm">
        <fieldset class="compare-picker">
          <legend>Elige los productos que quieres comparar</legend>
          <p class="compare-picker-hint">Marca uno o varios. La comparación se actualiza sola; puedes empezar con el producto actual y añadir otros.</p>
          <div class="compare-filters">
            <div class="compare-filter">
              <label class="compare-search-label" for="compareSearch">Buscar por nombre o código HS</label>
              <input type="search" id="compareSearch" class="compare-search" placeholder="Ej.: café o 090111" />
            </div>
            ${industryFilter}
          </div>
          <div class="compare-options">
            ${state.products
              .map(
                (p) => `
                  <label class="compare-option" data-product-name="${escapeHTML(`${p.name} ${p.hs6} ${p.industry || ''}`.toLowerCase())}" data-product-industry="${escapeHTML(p.industry || '')}">
                    <input type="checkbox" name="compareSlugs" value="${escapeHTML(p.slug)}"
                           ${state.compareSlugs.includes(p.slug) ? 'checked' : ''} />
                    <span class="compare-option-copy">
                      <span class="compare-option-name">${escapeHTML(p.name)}</span>
                      <span class="hs6">HS ${escapeHTML(p.hs6)}</span>
                      ${p.industry ? `<span class="chip chip-industry">${escapeHTML(p.industry)}</span>` : ''}
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
      </form>`
  }

  // Analysis view: selector + industry filter chips
  const industries = [...new Set(state.products.map((p) => p.industry).filter(Boolean))].sort()
  const industryChips = industries.length
    ? `
        <div class="filter-chips" id="analysisIndustryChips" role="group" aria-label="Filtrar por industria">
          <button type="button" class="filter-chip active" data-industry="">Todas</button>
          ${industries.map((name) => `<button type="button" class="filter-chip" data-industry="${escapeHTML(name)}">${escapeHTML(name)}</button>`).join('')}
        </div>`
    : ''

  const form = `
    <div class="controls-form" id="controlsForm">
      ${industryChips}
      ${renderCustomSelect()}
    </div>`

  return `${tabs}${form}`
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
    // Agrupa cambios seguidos (marcar varios) en una sola peticion a la API.
    let reloadTimer = null
    const scheduleReload = () => {
      updateSelectionCount()
      window.clearTimeout(reloadTimer)
      reloadTimer = window.setTimeout(refreshComparison, 300)
    }
    checkboxes.forEach((input) => input.addEventListener('change', scheduleReload))

    const searchInput = document.getElementById('compareSearch')
    const industryChips = comparisonForm.querySelectorAll('#compareIndustryChips .filter-chip')
    // Filtra la lista por texto (nombre/HS/industria) y por industria elegida.
    const applyProductFilter = () => {
      const query = searchInput.value.trim().toLowerCase()
      const activeChip = comparisonForm.querySelector('#compareIndustryChips .filter-chip.active')
      const industry = activeChip ? activeChip.dataset.industry : ''
      comparisonForm.querySelectorAll('.compare-option').forEach((option) => {
        const matchesQuery = option.dataset.productName.includes(query)
        const matchesIndustry = !industry || option.dataset.productIndustry === industry
        option.hidden = !(matchesQuery && matchesIndustry)
      })
    }
    searchInput.addEventListener('input', applyProductFilter)
    industryChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        industryChips.forEach((c) => c.classList.remove('active'))
        chip.classList.add('active')
        applyProductFilter()
      })
    })

    document.getElementById('selectAllProducts').addEventListener('click', () => {
      // Marca todos y limpia los filtros: el boton dice "Seleccionar todos", no
      // "los filtrados". Si no, con una busqueda o industria puesta solo se
      // comparaban los visibles y parecia que faltaba informacion.
      checkboxes.forEach((input) => {
        input.checked = true
      })
      searchInput.value = ''
      const allChip = comparisonForm.querySelector('#compareIndustryChips .filter-chip[data-industry=""]')
      industryChips.forEach((c) => c.classList.remove('active'))
      if (allChip) allChip.classList.add('active')
      applyProductFilter()
      scheduleReload()
    })
    document.getElementById('clearProducts').addEventListener('click', () => {
      checkboxes.forEach((input) => {
        input.checked = false
      })
      scheduleReload()
    })
    updateSelectionCount()

    comparisonForm.addEventListener('submit', (event) => {
      event.preventDefault()
      window.clearTimeout(reloadTimer)
      refreshComparison()
    })

    // Comportamiento nativo label+checkbox: no necesita handler extra
    // El listener 'change' en checkboxes ya llama a scheduleReload

    return
  }

  const form = document.getElementById('controlsForm')
  if (!form) return

  // --- Custom Select binding (Analysis view) ---
  bindCustomSelect(form, onChange)

  // Analysis view: industry filter chips (sync with custom select)
  const analysisChips = form.querySelectorAll('#analysisIndustryChips .filter-chip')
  if (analysisChips.length) {
    analysisChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        analysisChips.forEach((c) => c.classList.remove('active'))
        chip.classList.add('active')
        const industry = chip.dataset.industry
        // Filter custom select options
        filterCustomSelectOptions(form, industry)
        // Sync native select for form submission
        syncNativeSelect(form, industry)
        // Select first visible option
        selectFirstVisibleCustomOption(form)
      })
    })
  }
}

/** Vincula el comportamiento del custom select (abrir/cerrar, teclado, búsqueda, selección). */
function bindCustomSelect(form, onChange) {
  const trigger = form.querySelector('#customSelectTrigger')
  const dropdown = form.querySelector('#customSelectDropdown')
  const optionsContainer = form.querySelector('#customSelectOptions')
  const searchInput = form.querySelector('#customSelectDropdown .custom-select-search')
  const nativeSelect = form.querySelector('#productSelect')
  const hasSearch = !!searchInput
  if (!trigger || !dropdown || !optionsContainer) return

  let highlightedIndex = -1
  let allOptions = []

  // Inicializa la lista de opciones
  function refreshOptionsList() {
    allOptions = Array.from(optionsContainer.querySelectorAll('[role="option"]'))
    highlightedIndex = -1
  }

  // Abre el dropdown
  function openDropdown() {
    dropdown.hidden = false
    trigger.setAttribute('aria-expanded', 'true')
    if (hasSearch) {
      searchInput.value = ''
      filterDropdownOptions('')
    }
    refreshOptionsList()
    highlightOption(0)
    if (hasSearch) searchInput.focus()
    else trigger.focus()
    document.addEventListener('click', handleOutsideClick)
    document.addEventListener('keydown', handleKeydown)
  }

  // Cierra el dropdown
  function closeDropdown() {
    dropdown.hidden = true
    trigger.setAttribute('aria-expanded', 'false')
    if (hasSearch) searchInput.value = ''
    filterDropdownOptions('')
    document.removeEventListener('click', handleOutsideClick)
    document.removeEventListener('keydown', handleKeydown)
    trigger.focus()
  }

  function toggleDropdown() {
    if (dropdown.hidden) openDropdown()
    else closeDropdown()
  }

  // Click fuera cierra
  function handleOutsideClick(e) {
    if (!form.contains(e.target)) closeDropdown()
  }

  // Navegación por teclado
  function handleKeydown(e) {
    const options = Array.from(optionsContainer.querySelectorAll('[role="option"]:not([hidden])'))
    if (!options.length) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        highlightedIndex = Math.min(highlightedIndex + 1, options.length - 1)
        highlightOption(highlightedIndex)
        scrollIntoView(options[highlightedIndex])
        break
      case 'ArrowUp':
        e.preventDefault()
        highlightedIndex = Math.max(highlightedIndex - 1, 0)
        highlightOption(highlightedIndex)
        scrollIntoView(options[highlightedIndex])
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        if (highlightedIndex >= 0 && options[highlightedIndex]) {
          selectOption(options[highlightedIndex])
        }
        break
      case 'Escape':
        e.preventDefault()
        closeDropdown()
        break
      case 'Tab':
        closeDropdown()
        break
    }
  }

  function highlightIndex(idx) {
    highlightedIndex = idx
    refreshOptionsList()
    const options = Array.from(optionsContainer.querySelectorAll('[role="option"]:not([hidden])'))
    options.forEach((opt, i) => {
      opt.classList.toggle('highlighted', i === highlightedIndex)
      opt.setAttribute('aria-selected', i === highlightedIndex)
    })
  }

  function highlightOption(idx) {
    highlightIndex(idx)
  }

  function scrollIntoView(el) {
    if (el) el.scrollIntoView({ block: 'nearest' })
  }

  // Filtra opciones del dropdown por texto de búsqueda
  function filterDropdownOptions(query) {
    const q = query.trim().toLowerCase()
    const optionElements = optionsContainer.querySelectorAll('[role="option"]')
    optionElements.forEach((opt) => {
      const text = opt.textContent.toLowerCase()
      const matches = !q || text.includes(q)
      opt.hidden = !matches
    })
    refreshOptionsList()
    highlightOption(0)
  }

  // Selecciona una opción
  function selectOption(option) {
    const value = option.dataset.value
    const label = option.textContent.trim()
    trigger.querySelector('.custom-select-value').textContent = label
    trigger.setAttribute('aria-activedescendant', option.id)
    // Sync native select
    nativeSelect.value = value
    // Sync state
    state.slug = value
    syncURL()
    closeDropdown()
    onChange()
  }

  function filterCustomSelectOptions(form, industry) {
    const optionElements = form.querySelectorAll('#customSelectOptions [role="option"]')
    optionElements.forEach((opt) => {
      const optIndustry = opt.dataset.industry || ''
      const matches = !industry || optIndustry === industry
      opt.hidden = !matches
    })
    refreshOptionsList()
    highlightOption(0)
  }

  function syncNativeSelect(form, industry) {
    const nativeSelect = form.querySelector('#productSelect')
    Array.from(nativeSelect.options).forEach((opt) => {
      const optIndustry = opt.dataset.industry || ''
      opt.hidden = industry && optIndustry !== industry
    })
    // Select first visible in native
    const firstVisible = Array.from(nativeSelect.options).find((o) => !o.hidden)
    if (firstVisible) nativeSelect.value = firstVisible.value
  }

  function selectFirstVisibleCustomOption(form) {
    const optionsContainer = form.querySelector('#customSelectOptions')
    const firstVisible = Array.from(optionsContainer.querySelectorAll('[role="option"]:not([hidden])'))[0]
    if (firstVisible) selectOption(firstVisible)
  }

  // Event listeners
  trigger.addEventListener('click', (e) => {
    e.preventDefault()
    toggleDropdown()
  })
  trigger.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
      e.preventDefault()
      if (dropdown.hidden) openDropdown()
    }
  })
  searchInput.addEventListener('input', (e) => filterDropdownOptions(e.target.value))
  searchInput.addEventListener('keydown', (e) => e.stopPropagation()) // Evita que Tab cierre al buscar
  searchInput.addEventListener('click', (e) => e.stopPropagation())

  // Delegación de click en opciones
  optionsContainer.addEventListener('click', (e) => {
    const option = e.target.closest('[role="option"]')
    if (option && !option.hidden) selectOption(option)
  })

  refreshOptionsList()
}

/**
 * Enlaza el formulario del simulador. Vive dentro de #app, así que se recrea en
 * cada render: por eso el binding va aquí y no una sola vez al arranque. El
 * Los sliders empiezan sin seleccionar un supuesto, y el reset los limpia.
 */
function bindSimulator() {
  const form = document.getElementById('simulatorForm')
  if (!form) return

  const fields = {
    capex: 'simCapex',
    variableCost: 'simVar',
    year1Volume: 'simYear1Volume',
    annualGrowth: 'simAnnualGrowth',
    opex: 'simOpex',
    discountRate: 'simWacc',
  }
  const numbers = Object.entries(fields).map(([key, id]) => ({
    key,
    range: document.getElementById(id),
    output: document.getElementById(`${id}Value`),
  }))
  let timer = null
  let requestId = 0

  const numberValue = (range) => {
    if (range.dataset.configured !== 'true') return ''
    return String(Number(range.value))
  }

  const updateOutput = ({ range, output }) => {
    if (!output) return
    const digits = range.step.includes('.') ? range.step.split('.')[1].length : 0
    output.value = range.dataset.configured !== 'true'
      ? 'Por definir'
      : new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(Number(range.value))
  }

  const syncState = () => {
    numbers.forEach(({ key, range }) => {
      state[key] = numberValue(range)
    })
    syncURL()
  }

  const showPending = (message) => {
    const status = document.getElementById('evaluationStatus')
    if (status) status.textContent = message
    const results = document.getElementById('evaluationResults')
    if (results) {
      results.innerHTML = `
        <section class="card evaluation-pending">
          <h2>Resultados de la evaluación</h2>
          <p class="note">${escapeHTML(message)}</p>
        </section>${monteCarloRisk(null)}`
    }
  }

  const complete = () => {
    const year1Volume = document.getElementById('simYear1Volume')
    year1Volume.setCustomValidity(
      Number(year1Volume.value) <= 0
        ? 'El volumen del año 1 debe ser mayor que cero.'
        : ''
    )
    return numbers.every(({ range }) => range.dataset.configured === 'true') && form.checkValidity()
  }

  const refreshResults = async () => {
    syncState()
    if (!complete()) {
      requestId += 1
      showPending('Selecciona todos los supuestos con los sliders. El volumen del año 1 debe ser mayor que cero.')
      return
    }

    const currentRequest = ++requestId
    const status = document.getElementById('evaluationStatus')
    if (status) status.textContent = 'Actualizando evaluación…'
    try {
      const result = await getAnalysis(state.slug, analysisOpts())
      if (currentRequest !== requestId) return
      const results = document.getElementById('evaluationResults')
      if (!results) return
      results.innerHTML = [
        missingAssumptions(result),
        investment(result.investment),
        sensitivity(result.investment),
        monteCarloRisk(result.investment),
      ].join('')
      renderFinancialCharts(result.investment)
      const exportLink = document.querySelector('.btn-export')
      if (exportLink) exportLink.href = getExportUrl(state.slug, analysisOpts())
      if (status) status.textContent = 'Evaluación actualizada con los valores seleccionados.'
    } catch (error) {
      if (currentRequest !== requestId) return
      const results = document.getElementById('evaluationResults')
      if (results) {
        results.innerHTML = `<section class="card"><div class="alert error">No se pudo actualizar la evaluación: ${escapeHTML(error.message)}</div></section>`
      }
      if (status) status.textContent = 'No se pudo actualizar la evaluación.'
    }
  }

  const scheduleRefresh = () => {
    syncState()
    requestId += 1
    if (!complete()) {
      window.clearTimeout(timer)
      showPending('Selecciona todos los supuestos con los sliders. El volumen del año 1 debe ser mayor que cero.')
      return
    }
    const status = document.getElementById('evaluationStatus')
    if (status) status.textContent = 'Ajustando supuestos…'
    window.clearTimeout(timer)
    timer = window.setTimeout(refreshResults, 250)
  }

  numbers.forEach((field) => {
    updateOutput(field)
    field.range.addEventListener('input', () => {
      field.range.dataset.configured = 'true'
      updateOutput(field)
      scheduleRefresh()
    })
  })

  const reset = document.getElementById('simReset')
  if (reset) {
    reset.addEventListener('click', () => {
      numbers.forEach(({ range, output }) => {
        range.value = '0'
        range.dataset.configured = 'false'
        updateOutput({ range, output })
      })
      syncState()
      window.clearTimeout(timer)
      requestId += 1
      showPending('Selecciona los supuestos operativos para calcular la evaluación.')
    })
  }
}

function render(result) {
  const app = document.getElementById('app')
  destroyCharts()

  if (result.error || (result.market && !result.market.available)) {
    showError(result.error || result.market?.message || 'Sin datos.')
    return
  }

  const product = result.product || {}
  const hasFinancialInputs = [
    state.year1Volume,
    state.annualGrowth,
    state.variableCost,
    state.capex,
    state.opex,
    state.discountRate,
  ].every((value) => value !== '')
  const evaluationResults = hasFinancialInputs && result.investment
    ? `${investment(result.investment)}${sensitivity(result.investment)}${monteCarloRisk(result.investment)}`
    : `${missingAssumptions(result) || `
        <section class="card evaluation-pending">
          <h2>Resultados de la evaluación</h2>
          <p class="note">No hay suficientes datos para calcular VAN, TIR, recuperación y flujos de caja.</p>
        </section>`}${monteCarloRisk(result.investment)}`
  const meta = `
    <section class="card">
      <h2>${escapeHTML(product.name || '')}</h2>
      <div class="meta">
        <span>HS-6 <b>${escapeHTML(product.hs6 || '')}</b></span>
        ${product.nandina ? `<span>Partida SUNAT <b>${escapeHTML(product.nandina)}</b></span>` : ''}
        ${product.industry ? `<span>Industria <b>${escapeHTML(product.industry)}</b></span>` : ''}
        <span>Último año con data <b>${result.market.latest_year}</b></span>
      </div>
    </section>`

  app.innerHTML = [
    meta,
    unitEconomics(result.pricing),
    market(result.market, result.import_demand),
    marketShare(result, state),
    projection(result.projection, state),
    sunatPrice(result),
    destinations(result.destinations),
    competitors(result.competitors),
    headroom(result.headroom),
    sources(result),
    `<section class="project-evaluation" id="projectEvaluation">
      ${simulatorPanel(result, state)}
      <div id="evaluationResults">${evaluationResults}</div>
    </section>`,
  ].join('')

  renderAll(result)
  bindSimulator()
  bindShareYear(result)
  bindProjectionMethod(result)
}

/**
 * Filtro de año del grafico circular de participacion de mercado. Como vive
 * dentro de #app se re-crea en cada render, asi que se enlaza aqui. Cambiar el
 * ano solo redibuja el donut con la rebanada de ese ano: no hace falta recargar
 * el analisis, y el año queda en la URL para poder compartir la vista.
 */
function bindShareYear(result) {
  const sel = document.getElementById('shareYear')
  if (!sel) return
  sel.addEventListener('change', () => {
    state.shareYear = Number(sel.value)
    syncURL()
    window.__shareYear = state.shareYear
    destroyCharts()
    const yearData = result.share_by_year?.by_year?.find((y) => y.year === state.shareYear)
    shareDonut(document.getElementById('chartShare'), yearData)
    projectionChart(document.getElementById('chartProjection'), result.projection)
  })
}

/**
 * Selector de método de proyección. Cambiar el método recarga el análisis
 * desde la API con el nuevo parámetro, ya que el cálculo se hace en el backend.
 */
function bindProjectionMethod(result) {
  const sel = document.getElementById('projectionMethod')
  if (!sel) return
  sel.addEventListener('change', async () => {
    state.projectionMethod = sel.value
    syncURL()
    // Recargar el análisis completo con el nuevo método de proyección
    const status = document.getElementById('evaluationStatus')
    if (status) status.textContent = 'Actualizando proyección…'
    try {
      const fresh = await getAnalysis(state.slug, analysisOpts())
      render(fresh)
    } catch (err) {
      showError(err.message)
    }
  })
}

function renderComparisonView() {
  destroyCharts()
  const app = document.getElementById('app')
  const detail = state.comparisonData ? comparison(state.comparisonData) : EMPTY_COMPARISON
  app.innerHTML = `<section class="comparison-page">${ranking(state.rankingData)}${detail}</section>`
  renderRankingChart(state.rankingData)
  if (state.comparisonData) renderComparisonCharts(state.comparisonData)
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
    // El ranking y la comparacion van juntos y sobre la MISMA seleccion: marcar
    // productos es la pregunta "de estos, por cual empezar" y la comparacion es
    // el detalle. Por eso el ranking ya no abarca el catalogo completo.
    if (!state.compareSlugs.length) {
      state.comparisonData = null
      state.rankingData = null
      renderComparisonView()
      return
    }
    try {
      const [data, rank] = await Promise.all([
        getComparison(state.compareSlugs),
        getRanking(state.compareSlugs),
      ])
      if (reqId !== load.reqId) return
      state.comparisonData = data
      state.rankingData = rank
      renderComparisonView()
    } catch (err) {
      showError(err.message)
    }
    return
  }

  try {
    const result = await getAnalysis(state.slug, analysisOpts())
    if (reqId !== load.reqId) return
    render(result)
  } catch (err) {
    showError(err.message)
  }
}

load.reqId = 0
load()
