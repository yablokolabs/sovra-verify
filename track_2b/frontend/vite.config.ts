import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Keep this a literal so the config needs no Node type definitions.
const API_TARGET = 'http://127.0.0.1:8080'

// The backend mounts the production build at /app, so `base` must match.
export default defineConfig({
  base: '/app/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/config': { target: API_TARGET, changeOrigin: true },
      '/health': { target: API_TARGET, changeOrigin: true },
      '/documents': { target: API_TARGET, changeOrigin: true },
      '/analyses': { target: API_TARGET, changeOrigin: true },
      '/findings': { target: API_TARGET, changeOrigin: true },
    },
  },
})
