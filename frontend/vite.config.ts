/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In dev, the SPA (localhost:5173) and the API (localhost:8000) are
    // different origins. Proxying /api through Vite's dev server means the
    // browser sees same-origin requests during local dev, avoiding CORS
    // entirely for that case; production still relies on the backend's
    // real CORS_ORIGINS config (see backend/README.md#production) since
    // there's no Vite dev server there.
    //
    // The target is configurable because "localhost:8000" is only correct
    // when running `npm run dev` directly on the host. Inside Docker
    // Compose, this container can't reach the backend container via
    // "localhost" — docker-compose.yml sets VITE_PROXY_TARGET to the
    // backend's service name instead (see that file).
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
