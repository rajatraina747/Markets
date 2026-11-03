import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: `npm run dev` proxies /api to the Python server (./markets serve).
// Prod: `npm run build` → dist/, served by the Python server itself.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5801,
    proxy: { '/api': 'http://127.0.0.1:5800' },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
