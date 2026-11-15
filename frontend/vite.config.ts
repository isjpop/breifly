/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { defineConfig, loadEnv } from 'vite'

/** Security headers declared in nginx.conf (the production server), reused by `vite preview`. */
function productionHeaders(): Record<string, string> {
  const conf = readFileSync(new URL('./nginx.conf', import.meta.url), 'utf8')
  const headers: Record<string, string> = {}
  for (const match of conf.matchAll(/^\s*add_header\s+([\w-]+)\s+"([^"]+)"\s+always;/gm)) {
    headers[match[1]] = match[2]
  }
  return headers
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      // In development the browser talks to Vite only; /api is forwarded to Flask,
      // so no CORS configuration is needed on the backend.
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    preview: {
      headers: productionHeaders(),
      proxy: {
        '/api': { target: env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000', changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      restoreMocks: true,
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,tsx}'],
        exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**', 'src/main.tsx', 'src/vite-env.d.ts', 'src/types/**'],
        thresholds: { lines: 80, functions: 80, statements: 80, branches: 75 },
      },
    },
  }
})
