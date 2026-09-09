import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // maplibre-gl ships a web worker Vite's dep optimizer can't pre-bundle correctly.
  optimizeDeps: { exclude: ["maplibre-gl"] },
})
