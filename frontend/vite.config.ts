import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Im Docker-Container: VITE_PROXY_TARGET=http://backend:8000
// Lokal:               http://localhost:8001
const backendUrl = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8001'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true, // 0.0.0.0 — nötig für Docker
    watch: {
      usePolling: true, // Windows/Docker: inotify funktioniert nicht, Polling nötig
      interval: 1000,
    },
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/media': {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
})
