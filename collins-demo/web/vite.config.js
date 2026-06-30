import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server on :5173. All /api calls are proxied to the orchestrator on :8090
// (the BFF), which runs the live-twin physics in-process — the web app never
// talks to a database or Docker.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,   // never drift to 5174/5175 — fail loudly instead
    proxy: {
      '/api': { target: 'http://localhost:8090', changeOrigin: true },
    },
  },
})
