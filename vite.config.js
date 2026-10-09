import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'

// El puerto del backend se lee de dev.config.json, la misma fuente que usa
// scripts/run-api.mjs. Si estuviera escrito aqui a mano, cambiar el puerto en
// un solo lugar dejaria el proxy apuntando al puerto viejo y la web cargaria
// con la API en error.
const dev = JSON.parse(readFileSync(new URL('./dev.config.json', import.meta.url), 'utf8'))
const API_TARGET = `http://${dev.host}:${dev.api}`

// Vite escucha en 'web_host', que por defecto es el loopback de 'host' y se
// puede cambiar en dev.config.json para abrir la web desde otro equipo sin
// tocar este archivo. El proxy SIEMPRE apunta a dev.host: por eso /api y /health
// siguen yendo al backend por loopback y no importa en que direccion se exponga
// el dev server.
const WEB_HOST = dev.web_host || dev.host

// El frontend vive en /frontend y habla con FastAPI.
//
// En desarrollo, Vite corre en el puerto de dev.config.json y hace proxy de
// /api y /health hacia uvicorn. Asi el navegador ve un solo origen, no hay
// CORS, y el codigo del frontend puede llamar a '/api/...' sin hardcodear el
// host del backend.
//
// En produccion, `vite build` emite dist/ con rutas relativas, para que el
// mismo build funcione servido por FastAPI, por nginx o por un CDN sin
// reconfiguracion.
export default defineConfig({
  root: 'frontend',
  base: './',
  publicDir: false,
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    // Los assets se emiten sin hash para que FastAPI pueda referenciarlos con
    // nombres estables.
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
  server: {
    host: WEB_HOST,
    port: dev.web,
    strictPort: true,
    watch: {
      // El codigo puede vivir en un share de red (SMB), y ahi el watching
      // nativo de Node no recibe eventos: falla con 'UNKNOWN: unknown error,
      // watch' y Vite se cae. El polling es mas lento, pero es el unico modo
      // que funciona sobre SMB. En un disco local se puede quitar.
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/health': { target: API_TARGET, changeOrigin: true },
    },
  },
})
