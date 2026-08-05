import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Recharts и Leaflet весят больше самого приложения и меняются редко —
        // выносим их в отдельные чанки, чтобы браузер кэшировал их между релизами.
        manualChunks: {
          charts: ['recharts'],
          maps: ['leaflet', 'react-leaflet'],
        },
      },
    },
  },
})
