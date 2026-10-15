/**
 * Genera dist/_redirects para desplegar la UI en Netlify.
 *
 * Netlify sirve estaticos y no corre Python: la API vive aparte (Render,
 * Railway, Fly...). Este archivo reenvia /api y /health a esa API para que el
 * navegador vea un solo origen, sin CORS y sin tocar el frontend (que usa rutas
 * relativas a proposito, ver frontend/js/api.js).
 *
 * La URL de la API sale de la variable de entorno API_URL, que se configura en
 * Netlify. Asi el repositorio no guarda una URL fija.
 */

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const apiUrl = (process.env.API_URL || '').trim().replace(/\/+$/, '')

if (!apiUrl) {
  console.warn('API_URL sin definir: la UI se publica sin backend (solo el diseno).')
  console.warn('Definela en Netlify -> Site configuration -> Environment variables.')
  process.exit(0)
}

// Gana la primera regla que coincide; el `!` fuerza el proxy aunque exista un
// archivo en esa ruta. El navegador solo ve el dominio de Netlify.
const redirects = [
  `/api/*  ${apiUrl}/api/:splat  200!`,
  `/health  ${apiUrl}/health  200!`,
  '',
].join('\n')

writeFileSync(join(root, 'dist', '_redirects'), redirects)
console.log(`dist/_redirects -> ${apiUrl}`)
