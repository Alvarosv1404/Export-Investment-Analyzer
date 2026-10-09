/**
 * Revisa que los puertos de dev.config.json esten libres antes de `npm run dev`.
 *
 * Correlo cuando algo falla al arrancar. El mensaje de uvicorn cuando el
 * puerto esta ocupado ("[Errno 10048]") no dice que otro proceso lo tiene, y
 * eso cuesta varios minutos de adivinar; este dice exactamente cual puerto,
 * quien lo tiene y que hacer.
 *
 * Ojo con `netstat -ano -p tcp`: el flag `-p tcp` deja fuera los sockets IPv6
 * (`[::1]:5180`), que es justo donde Vite se engancha cuando `localhost`
 * resuelve a IPv6. Sin el flag, salen IPv4 e IPv6 y el diagnostico es cierto.
 */

import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const config = JSON.parse(readFileSync(join(root, 'dev.config.json'), 'utf8'))
const isWindows = process.platform === 'win32'

function findOwner(port) {
  try {
    if (isWindows) {
      // Sin `-p tcp`: con ese flag, netstat omite los listeners IPv6.
      const out = execSync(`netstat -ano | findstr /R /C:":${port} .*LISTENING"`, { encoding: 'utf8' })
      const line = out.trim().split(/\r?\n/).find((l) => l.includes(`:${port}`) && l.includes('LISTENING'))
      const pid = line ? line.trim().split(/\s+/).pop() : null
      if (!pid) return null
      let name = 'proceso desconocido'
      try {
        const listed = execSync(`tasklist /FI "PID eq ${pid}" /FO CSV /NH`, { encoding: 'utf8' })
          .trim()
          .split(',')[0]
          .replace(/"/g, '')
        // tasklist sale con codigo 0 aunque no encuentre el PID, y devuelve un
        // texto largo en vez de un nombre. Si no parece un nombre de proceso,
        // se descarta: el PID probablemente ya no exista.
        if (/^[\w.+-]+$/.test(listed)) name = listed
      } catch {
        /* tasklist falla: dejamos el nombre generico */
      }
      return { pid, name }
    }
    const out = execSync(`lsof -iTCP:${port} -sTCP:LISTEN -P -n || true`, { encoding: 'utf8' })
    const lines = out.trim().split('\n').slice(1)
    if (!lines.length) return null
    const parts = lines[0].trim().split(/\s+/)
    return { pid: parts[1], name: parts[0] }
  } catch {
    return null
  }
}

let busy = 0
for (const [label, port] of [['API (FastAPI)', config.api], ['Web (Vite)', config.web]]) {
  const owner = findOwner(port)
  if (owner) {
    busy += 1
    console.error(`  OCUPADO  ${label}: puerto ${port} -> ${owner.name} (PID ${owner.pid})`)
  } else {
    console.log(`  libre    ${label}: puerto ${port}`)
  }
}

if (busy) {
  console.error('\n  Para liberarlos: cierra el proceso, o cambia el puerto en dev.config.json')
  process.exit(1)
}
console.log('\n  Todo listo para npm run dev.')
