import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server on :5174 (the existing NextXR frontend uses :5173). All /api calls
// are proxied to the orchestrator on :8090 — the web app never talks to the
// platforms directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': { target: 'http://localhost:8090', changeOrigin: true },
    },
  },
})
