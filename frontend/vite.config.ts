import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// import.meta.dirname is required by Vite 8's native ESM config loader (__dirname is CJS-only)
const __dirname = import.meta.dirname

// In dev: Vite dev server proxies /api/* to the FastAPI backend on :8000.
// In production (Docker): FastAPI serves the compiled dist/ as /static/dist/.
export default defineConfig(({ command }) => ({
  plugins: [react()],

  // Assets reference /static/dist/assets/... in prod so FastAPI's /static mount serves them.
  // In dev mode the base is / so the dev server works normally.
  base: command === 'build' ? '/static/dist/' : '/',

  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },

  build: {
    outDir: 'dist',
    sourcemap: false,
    // Keep chunk size reasonable; Bible chapters can be large
    chunkSizeWarningLimit: 800,
  },

  server: {
    port: 5173,
    proxy: {
      // All API and fragment requests go to the FastAPI dev server
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/fragments': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
}))
